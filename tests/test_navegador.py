"""Ponta a ponta no navegador: a página carrega o Pyodide, converte, copia e funciona sem rede.

Os testes da PWA (test_pwa.py) conferem a coerência dos arquivos, mas não abrem um
navegador. Estes abrem o Chromium do Playwright num perfil limpo, como numa primeira
visita, e fazem o que a pessoa faz: enviar o documento, omitir o cabeçalho, copiar o HTML
e, depois, converter de novo sem rede.

Ficam fora da suíte padrão (marca e2e): precisam do Chromium do Playwright e de rede para
o CDN do Pyodide, e levam perto de um minuto. Para rodar:

    uv sync --group e2e
    uv run playwright install chromium
    uv run pytest -m e2e
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e

DOCS = Path(__file__).resolve().parent.parent / "docs"
# O Pyodide vem do CDN na primeira visita: em rede lenta, o carregamento passa de um minuto
PRAZO_CARREGAMENTO_MS = 240_000
PRAZO_CONVERSAO_MS = 60_000
# O OCR de uma página leva segundos; o prazo cobre o download das bibliotecas numa rede lenta
PRAZO_OCR_MS = 120_000
# Atraso dos arquivos lentos no teste da troca de domínio
ATRASO_S = 2
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
# O que a página precisa do CDN para abrir e converter sem rede
ARQUIVOS_DO_PYODIDE = [
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
]

NOTA = (
    "# NOTA TÉCNICA Nº 12/2026/CGDI\n\n"
    "PROCESSO Nº 00000.000000/2026-00\n\n"
    "INTERESSADO: Coordenação-Geral\n\n"
    "## 1. ASSUNTO\n\n"
    "Texto do assunto.\n\n"
    "## 2. ANÁLISE\n\n"
    "Texto da análise.\n"
).encode()

LER_HTML_COPIADO = """async () => {
  const itens = await navigator.clipboard.read();
  const blob = await itens[0].getType('text/html');
  return blob.text();
}"""


# evaluate aguarda a Promise da função async. O wait_for_function não aguarda: a Promise
# conta como verdadeira, e uma espera assim passava sem conferir nada
TEM_NO_CACHE = """async (caminho) => {
  const nome = (await caches.keys()).find(n => n.startsWith('conversao-sei-estatico-'));
  return Boolean(nome && await (await caches.open(nome)).match(new URL(caminho, location.href)));
}"""
FALTANDO_NO_CACHE = """async (urls) => {
  const faltando = [];
  for (const url of urls) if (!(await caches.match(url))) faltando.push(url);
  return faltando;
}"""
APAGAR_DO_CACHE = """async (caminho) => {
  const nome = (await caches.keys()).find(n => n.startsWith('conversao-sei-estatico-'));
  return Boolean(nome) && (await caches.open(nome)).delete(new URL(caminho, location.href));
}"""


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass


class _Redirecionavel(_Silencioso):
    """Serve docs/ até ganhar um destino e daí redireciona tudo para ele, como o GitHub
    Pages faz com o caminho antigo quando o repositório passa a ter domínio próprio."""

    destino: str | None = None
    # Caminhos servidos com atraso, para a troca acontecer com a gravação no cache em curso
    lentos: frozenset[str] = frozenset()

    def do_GET(self) -> None:
        if self.destino:
            self.send_response(301)
            self.send_header("Location", self.destino + self.path.lstrip("/"))
            self.end_headers()
            return
        if self.path.split("?")[0] in self.lentos:
            time.sleep(ATRASO_S)
        super().do_GET()


@pytest.fixture
def servidor() -> Iterator[ThreadingHTTPServer]:
    """Serve docs/ como o GitHub Pages serve, numa porta livre. Um por teste: o teste
    desliga o servidor para simular a falta de rede."""
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(DOCS)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture
def endereco(servidor: ThreadingHTTPServer) -> str:
    return f"http://127.0.0.1:{servidor.server_address[1]}/"


@pytest.fixture(params=["chromium", "webkit"])
def contexto(request: pytest.FixtureRequest, endereco: str) -> Iterator[object]:
    with sync_api.sync_playwright() as p:
        navegador = getattr(p, request.param).launch()
        # O WebKit não conhece clipboard-write: a escrita nele só exige o clique
        permissoes = ["clipboard-read"] if request.param == "webkit" else ["clipboard-read", "clipboard-write"]
        ctx = navegador.new_context(permissions=permissoes)
        # O teste não pode virar visita nem conversão na contagem de acessos do site
        ctx.route("https://gc.zgo.at/**", lambda rota: rota.abort())
        ctx.route("https://*.goatcounter.com/**", lambda rota: rota.abort())
        yield ctx
        navegador.close()


def _esperar_conversor(pagina: object) -> None:
    pagina.wait_for_function(  # type: ignore[attr-defined]
        "() => !document.getElementById('file-input').disabled", timeout=PRAZO_CARREGAMENTO_MS
    )


PAGINA_HTML = (
    b'<html><head><title>Aba</title></head><body><script>alert(1)</script>'
    b'<p class="Texto_Ementa">Ementa lida de HTML.</p><p>Texto.</body></html>'
)


def _enviar(pagina: object) -> None:
    pagina.set_input_files(  # type: ignore[attr-defined]
        "#file-input", files=[{"name": "nota.md", "mimeType": "text/markdown", "buffer": NOTA}]
    )


def _pdf_sem_texto() -> bytes:
    """Uma página em branco, como um PDF digitalizado: nada a extrair."""
    from io import BytesIO

    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    saida = BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def _copiar(pagina: object) -> str:
    """Copia a primeira parte e devolve o text/html gravado.

    Espera o "Copiado" do botão, que só aparece quando o HTML foi gravado com formatação:
    ler antes disso pega a área de transferência no meio da escrita.
    """
    pagina.click("button.btn-copy")  # type: ignore[attr-defined]
    pagina.locator("button.btn-copy .rotulo-copiado:not(.invisible)").wait_for(  # type: ignore[attr-defined]
        timeout=PRAZO_CONVERSAO_MS
    )
    return pagina.evaluate(LER_HTML_COPIADO)  # type: ignore[attr-defined]


def _esperar_no_cache(pagina: object, caminho: str, prazo_s: float = 60) -> None:
    """Espera o arquivo voltar ao cache do service worker, consultando até o prazo."""
    limite = time.monotonic() + prazo_s
    while not pagina.evaluate(TEM_NO_CACHE, caminho):  # type: ignore[attr-defined]
        assert time.monotonic() < limite, f"{caminho} não voltou ao cache do service worker"
        time.sleep(0.2)


def test_converte_omite_cabecalho_copia_e_funciona_sem_rede(
    contexto: object, endereco: str, servidor: ThreadingHTTPServer
) -> None:
    pagina = contexto.new_page()  # type: ignore[attr-defined]
    erros: list[str] = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))

    # Primeira visita: carrega o Pyodide do CDN e converte
    pagina.goto(endereco)
    _esperar_conversor(pagina)
    _enviar(pagina)
    pagina.locator("button.btn-copy").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    assert pagina.locator("#results-section").evaluate(
        "el => el.previousElementSibling.id === 'pyodide-status-card'"
    )
    assert "3 parágrafos incluídos" in pagina.locator("#res-cabecalho-resumo").inner_text()
    assert not pagina.locator("#res-ajustes").evaluate("el => el.open")
    pagina.locator("#res-ajustes summary").click()
    cartao = pagina.locator("#res-cabecalho-card")
    cartao.wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    assert "3 parágrafos vêm antes do item 1" in cartao.inner_text()

    # O resumo da conversão fica só para o leitor de tela (o quadro do resultado já diz o
    # mesmo), o limite só aparece quando o arquivo não cabe, e Copiar é o único botão
    # principal da tela
    assert pagina.locator("#pyodide-status-card").evaluate("el => el.classList.contains('sr-only')")
    assert "Cabe no limite" not in pagina.locator("#res-parts-list").inner_text()
    assert "bg-white" in (pagina.locator("#btn-selecionar").get_attribute("class") or "")

    marca = pagina.locator("[data-parte='0'] [data-marca-copiada]")
    assert marca.is_hidden()
    copiado = _copiar(pagina)
    assert "NOTA TÉCNICA" in copiado
    assert 'class="Item_Nivel1"' in copiado
    # A marca de parte copiada fica depois que o "Copiado" do botão some
    assert marca.is_visible()

    # Omitir cabeçalho converte de novo, e o HTML copiado começa no item 1
    pagina.click("#btn-cabecalho")
    pagina.locator("#btn-cabecalho", has_text="Restaurar cabeçalho").wait_for(timeout=PRAZO_CONVERSAO_MS)
    pagina.wait_for_function("() => !document.getElementById('results-section').inert")
    copiado = _copiar(pagina)
    assert "NOTA TÉCNICA" not in copiado and "PROCESSO" not in copiado
    assert 'class="Item_Nivel1"' in copiado
    assert "Texto da análise." in copiado

    # O relato de problema monta o e-mail com os dados técnicos, e nunca com o nome do arquivo
    relato = unquote(pagina.evaluate("() => linkDoRelato()"))
    assert relato.startswith("mailto:conversorsei@gmail.com?subject=")
    assert "Versão da página:" in relato and "Formato: .md" in relato
    assert "Conversão concluída" in relato
    assert "nota" not in relato.lower()

    # A sugestão vai para o mesmo e-mail, com assunto próprio e sem os dados técnicos
    sugestao = unquote(pagina.get_attribute("[data-sugestao]", "href"))
    assert sugestao.startswith("mailto:conversorsei@gmail.com?subject=Conversor SEI: sugestão")
    assert "Versão da página:" not in sugestao and "Navegador:" not in sugestao
    assert "nota" not in sugestao.lower()

    # Apoio por Pix: a janela mostra o QR Code e copia o mesmo código do QR Code
    pagina.click("#btn-apoio")
    pagina.locator("#pix-modal").wait_for(state="visible")
    assert pagina.evaluate("() => document.getElementById('pix-qrcode').naturalWidth > 0")
    pagina.click("#pix-copiar-codigo")
    pagina.locator("#toast-message", has_text="Código Pix copiado").wait_for(timeout=5_000)
    assert pagina.evaluate("async () => (await navigator.clipboard.readText()) === PIX_COPIA_E_COLA")
    pagina.keyboard.press("Escape")
    pagina.locator("#pix-modal").wait_for(state="hidden")

    # Um arquivo que não abre mostra o erro com o link de relato, também sem o nome
    pagina.set_input_files(
        "#file-input",
        files=[{"name": "Parecer Sigiloso 12.docx", "mimeType": "application/octet-stream", "buffer": b"quebrado"}],
    )
    pagina.locator("#status-relato").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    relato = unquote(pagina.evaluate("() => linkDoRelato()"))
    assert "Formato: .docx" in relato and "Situação: Erro ao converter documento" in relato
    assert "Sigiloso" not in relato and "Parecer" not in relato and "<arquivo>" in relato
    assert pagina.locator("#status-ocr-iniciar").is_hidden()

    # PDF sem camada de texto: o erro oferece o OCR, e a conversão seguinte o esconde
    pagina.set_input_files(
        "#file-input", files=[{"name": "digitalizado.pdf", "mimeType": "application/pdf", "buffer": _pdf_sem_texto()}]
    )
    pagina.locator("#status-ocr-iniciar").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    _enviar(pagina)
    pagina.locator("#status-ocr-iniciar").wait_for(state="hidden", timeout=PRAZO_CONVERSAO_MS)
    pagina.locator("#status-relato").wait_for(state="hidden", timeout=PRAZO_CONVERSAO_MS)

    # HTML converte no navegador pelo html.parser do Pyodide, com a classe do SEI intacta
    pagina.set_input_files(
        "#file-input",
        files=[{"name": "pagina.html", "mimeType": "text/html", "buffer": PAGINA_HTML}],
    )
    pagina.locator("#res-parts-list", has_text="pagina_SEI.html").wait_for(timeout=PRAZO_CONVERSAO_MS)
    copiado = _copiar(pagina)
    assert 'class="Texto_Ementa"' in copiado and "Ementa lida de HTML." in copiado
    assert "alert" not in copiado

    # O service worker precisa ter guardado o Pyodide, e não só o cache HTTP do navegador,
    # que pode ser descartado a qualquer momento
    pagina.wait_for_function("() => navigator.serviceWorker.controller !== null", timeout=PRAZO_CONVERSAO_MS)
    # O reparo pedido pela página completa o que o carregamento não guardou (no WebKit, o
    # pyodide.asm.js), então a conferência espera por ele
    urls = [PYODIDE + nome for nome in ARQUIVOS_DO_PYODIDE]
    limite = time.monotonic() + 60
    while faltando := pagina.evaluate(FALTANDO_NO_CACHE, urls):
        assert time.monotonic() < limite, f"Fora do cache do service worker: {faltando}"
        time.sleep(0.2)

    # Simula uma falha parcial do pré-cache e confirma que a página pronta pede o reparo.
    assert pagina.evaluate(APAGAR_DO_CACHE, "index.html"), "index.html não estava no pré-cache"
    pagina.add_init_script(
        """(() => {
          window.mensagensDeReparo = [];
          const enviar = ServiceWorker.prototype.postMessage;
          ServiceWorker.prototype.postMessage = function(dados, ...args) {
            window.mensagensDeReparo.push(dados);
            return enviar.call(this, dados, ...args);
          };
        })();"""
    )
    pagina.reload()
    _esperar_conversor(pagina)
    pagina.wait_for_function(
        "() => window.mensagensDeReparo.some(dados => dados.tipo === 'reparar-cache-essencial')",
        timeout=5_000,
    )
    _esperar_no_cache(pagina, "index.html")

    # A segunda exclusão isola o reparo: não há navegação nem carregamento de recurso.
    assert pagina.evaluate(APAGAR_DO_CACHE, "index.html")
    pagina.evaluate("() => navigator.serviceWorker.controller.postMessage({tipo: 'reparar-cache-essencial'})")
    _esperar_no_cache(pagina, "index.html")

    # Sem rede: a página abre e converte com o que ficou guardado. A falta de rede é o site
    # fora do ar e o CDN bloqueado. O modo offline do Playwright não serve: no WebKit, ele
    # derruba a navegação antes de ela chegar ao service worker
    servidor.shutdown()
    servidor.server_close()
    contexto.route("https://cdn.jsdelivr.net/**", lambda rota: rota.abort())  # type: ignore[attr-defined]
    pagina.reload()
    _esperar_conversor(pagina)
    _enviar(pagina)
    pagina.locator("#results-section").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    assert "Item_Nivel1" in _copiar(pagina)

    assert erros == []


def test_troca_de_dominio_leva_ao_endereco_novo_e_desliga_o_service_worker(
    contexto: object, endereco: str
) -> None:
    """Com o domínio próprio, o GitHub Pages redireciona o endereço antigo, inclusive o
    sw.js. O service worker antigo tem de repassar o redirecionamento ao navegador e sair
    do caminho: seguido por ele, a página não abria, e o navegador não o atualiza por um
    redirecionamento. Os dois servidores locais, em portas diferentes, são duas origens."""
    antigo_handler = type("_Antigo", (_Redirecionavel,), {"destino": None})
    antigo = ThreadingHTTPServer(("127.0.0.1", 0), partial(antigo_handler, directory=str(DOCS)))
    threading.Thread(target=antigo.serve_forever, daemon=True).start()
    endereco_antigo = f"http://127.0.0.1:{antigo.server_address[1]}/"
    # O teste é do service worker: o Pyodide não precisa carregar
    contexto.route("https://cdn.jsdelivr.net/**", lambda rota: rota.abort())  # type: ignore[attr-defined]
    try:
        pagina = contexto.new_page()  # type: ignore[attr-defined]
        pagina.goto(endereco_antigo)
        pagina.wait_for_function(
            "() => navigator.serviceWorker.controller !== null", timeout=PRAZO_CONVERSAO_MS
        )
        _esperar_no_cache(pagina, "index.html")

        # Gravações em curso na hora da troca: o reparo do cache, que roda no service
        # worker, e uma busca da página. As duas terminam depois do desligamento
        antigo_handler.lentos = frozenset({"/index.html", "/manifest.webmanifest"})
        assert pagina.evaluate(APAGAR_DO_CACHE, "index.html")
        pagina.evaluate("() => navigator.serviceWorker.controller.postMessage({tipo: 'reparar-cache-essencial'})")
        pagina.evaluate("() => { fetch('manifest.webmanifest?lento'); }")
        time.sleep(0.5)

        antigo_handler.destino = endereco
        pagina.goto(endereco_antigo)
        assert pagina.url.startswith(endereco)
        time.sleep(ATRASO_S + 1)

        # De volta ao endereço antigo, fora da página: sem service worker, o servidor
        # responde direto, e o 404 prova que nada mais intercepta a navegação
        antigo_handler.destino = None
        antigo_handler.lentos = frozenset()
        resposta = pagina.goto(endereco_antigo + "nao-existe")
        assert resposta.status == 404
        assert pagina.evaluate("async () => (await navigator.serviceWorker.getRegistrations()).length") == 0
        restantes = pagina.evaluate("async () => (await caches.keys()).filter(n => n.startsWith('conversao-sei-'))")
        assert restantes == [], f"Caches que sobraram no endereço antigo: {restantes}"
    finally:
        antigo.shutdown()
        antigo.server_close()


PAGINA_DIGITALIZADA = """<!doctype html><html><body style="margin:0;background:#fff">
<div style="padding:90px 80px;font:22px/1.6 'Times New Roman',serif;color:#000">
<p><b>1. ASSUNTO</b></p>
<p>1.1. Proposta de padronizacao dos relatorios mensais das unidades regionais.</p>
<p><b>2. CONCLUSAO</b></p>
<p>2.1. Recomenda-se aprovar a proposta a partir do proximo trimestre.</p>
</div></body></html>"""


# Colagem simulada: o Playwright não escreve text/html na área de transferência de todos
# os navegadores, então o evento de colar é disparado com os dados prontos
COLAR = """([seletor, dados]) => {
  const transferencia = new DataTransfer();
  for (const [tipo, valor] of Object.entries(dados)) transferencia.setData(tipo, valor);
  document.querySelector(seletor).dispatchEvent(
    new ClipboardEvent('paste', { clipboardData: transferencia, bubbles: true, cancelable: true })
  );
}"""


def _resultado_com(pagina: object, trecho: str) -> None:
    pagina.wait_for_function(  # type: ignore[attr-defined]
        "trecho => currentResultFiles.some(arq => arq.conteudo.includes(trecho))", arg=trecho,
        timeout=PRAZO_CONVERSAO_MS,
    )


def test_texto_colado_converte_como_um_arquivo(contexto: object, endereco: str) -> None:
    pagina = contexto.new_page()  # type: ignore[attr-defined]
    erros: list[str] = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))
    pagina.goto(endereco)
    _esperar_conversor(pagina)

    # HTML de um editor, colado em qualquer ponto da página: vai ao leitor de HTML
    pagina.evaluate(
        COLAR,
        ["body", {"text/html": '<p class="Texto_Ementa">Ementa colada.</p><p>Texto.</p>',
                  "text/plain": "Ementa colada.\nTexto."}],
    )
    pagina.locator("#res-filename", has_text="Texto colado").wait_for(timeout=PRAZO_CONVERSAO_MS)
    assert "texto_colado_SEI.html" in pagina.locator("#res-parts-list").inner_text()
    copiado = _copiar(pagina)
    assert 'class="Texto_Ementa"' in copiado and "Ementa colada." in copiado
    assert "Formato: colado (.html)" in unquote(pagina.evaluate("() => linkDoRelato()"))

    # O botão Copiar dos chats de IA entrega só texto simples, com as marcas do Markdown
    pagina.evaluate(COLAR, ["body", {"text/plain": "## 1. ASSUNTO\n\nTexto com **negrito**."}])
    _resultado_com(pagina, 'class="Item_Nivel1"')
    _resultado_com(pagina, "<strong>negrito</strong>")

    # Colar num campo das opções é só colar: não converte
    selecao = pagina.evaluate("() => numeroDaSelecao")
    pagina.evaluate(COLAR, ["#opt-max-kb", {"text/plain": "20"}])
    assert pagina.evaluate("() => numeroDaSelecao") == selecao

    # No celular, o botão abre o campo, e colar nele converte e o fecha
    pagina.click("#btn-colar")
    pagina.locator("#colar-campo").wait_for(state="visible")
    assert pagina.evaluate("() => document.activeElement.id") == "colar-campo"
    pagina.evaluate(COLAR, ["#colar-campo", {"text/plain": "Colado no campo."}])
    _resultado_com(pagina, "Colado no campo.")
    assert pagina.locator("#colar-painel").is_hidden()

    # Texto digitado no campo converte pelo botão
    pagina.click("#btn-colar")
    pagina.fill("#colar-campo", "Digitado no campo.")
    pagina.click("#btn-colar-converter")
    _resultado_com(pagina, "Digitado no campo.")
    assert not erros, erros


def _pdf_de_imagem(jpeg: bytes, largura: int, altura: int) -> bytes:
    """PDF de uma página A4 que só tem uma imagem JPEG, como um documento digitalizado."""
    conteudo = b"q 595 0 0 842 0 0 cm /Im0 Do Q"
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
        b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (largura, altura, len(jpeg))
        + jpeg + b"\nendstream",
        b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    posicoes = []
    for numero, corpo in enumerate(objetos, start=1):
        posicoes.append(len(pdf))
        pdf += b"%d 0 obj\n" % numero + corpo + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % p for p in posicoes)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return pdf


# Apaga, na página e no worker do PDF.js, os recursos de JavaScript que um navegador menos
# atualizado não tem. O script de inicialização do Playwright não roda dentro dos workers:
# o worker do PDF.js é trocado por um módulo que apaga os recursos e só então importa o
# original, em dois módulos porque os import estáticos rodam antes do resto do arquivo.
# `__WORKER__` é o que o módulo importa: o endereço pedido pela página, ou outro no lugar
SEM_RECURSOS_NOVOS_NA_PAGINA_E_NOS_WORKERS = """
(() => {
  const apagar = `
    for (const tipo of [Map, WeakMap])
      for (const nome of ['getOrInsert', 'getOrInsertComputed']) delete tipo.prototype[nome];
    delete Promise.withResolvers;
  `;
  new Function(apagar)();
  const WorkerOriginal = window.Worker;
  window.Worker = function (url, opcoes) {
    const endereco = new URL(url, location.href).href;
    if (!endereco.includes('pdfjs')) return new WorkerOriginal(url, opcoes);
    const alvo = new URL(__WORKER__ || endereco, location.href).href;
    const modulo = (codigo) => URL.createObjectURL(new Blob([codigo], { type: 'text/javascript' }));
    const entrada = modulo(`import '${modulo(apagar)}'; import '${alvo}';`);
    return new WorkerOriginal(entrada, { ...opcoes, type: 'module' });
  };
  window.Worker.prototype = WorkerOriginal.prototype;
})();
"""


def _sem_recursos_novos(worker: str | None = None) -> str:
    """Script de inicialização que simula o navegador menos atualizado. Com `worker`, o
    worker do PDF.js importa esse endereço no lugar do pedido pela página."""
    return SEM_RECURSOS_NOVOS_NA_PAGINA_E_NOS_WORKERS.replace("__WORKER__", repr(worker) if worker else "null")


def test_ocr_reconhece_o_texto_de_um_pdf_digitalizado(contexto: object, endereco: str) -> None:
    """PDF sem camada de texto: o botão do erro reconhece as páginas no navegador, e o
    texto segue a conversão do PDF, com o aviso para conferir. Mudar uma opção converte
    de novo com o mesmo texto, sem pedir o OCR outra vez."""
    pagina = contexto.new_page()  # type: ignore[attr-defined]
    erros: list[str] = []
    pagina.on("pageerror", lambda erro: erros.append(str(erro)))
    console: list[str] = []
    pagina.on("console", lambda msg: console.append(f"{msg.type}: {msg.text}"))
    # Simula um navegador sem os recursos mais novos que o PDF.js usa, como o Samsung
    # Internet do Android: o Playwright usa navegadores de última versão, que os têm
    pagina.add_init_script(_sem_recursos_novos())

    # A "digitalização": o texto vira imagem, sem nenhuma fonte no PDF
    pagina.set_viewport_size({"width": 794, "height": 1123})
    pagina.set_content(PAGINA_DIGITALIZADA)
    jpeg = pagina.screenshot(type="jpeg", quality=90)
    pdf = _pdf_de_imagem(jpeg, 794, 1123)

    pagina.goto(endereco)
    _esperar_conversor(pagina)
    pagina.set_input_files(
        "#file-input", files=[{"name": "digitalizado.pdf", "mimeType": "application/pdf", "buffer": pdf}]
    )
    pagina.locator("#status-ocr-iniciar").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    pagina.click("#status-ocr-iniciar")
    # Termina no resultado ou num erro: esperar só o resultado deixava um erro do OCR
    # parado até o fim do prazo, sem dizer qual era
    pagina.wait_for_function(
        "() => document.querySelector('button.btn-copy')"
        " || !document.getElementById('status-relato').classList.contains('hidden')",
        timeout=PRAZO_OCR_MS,
    )
    if not pagina.locator("button.btn-copy").count():
        # O quadro de situação mostra a etapa e o andamento do OCR, ou o erro
        situacao = pagina.locator("#pyodide-status-card").inner_text()
        pytest.fail(f"O OCR não terminou. Situação: {situacao!r}. Console: {console[-20:]} Erros: {erros}")

    html = pagina.evaluate("() => currentResultFiles[0].conteudo")
    assert 'class="Item_Nivel1"' in html
    assert "ASSUNTO" in html and "CONCLUSAO" in html
    assert "padronizacao dos relatorios mensais" in html
    avisos = pagina.locator("#res-warnings-list").inner_text()
    assert "reconhecido por OCR e pode ter erros" in avisos and "Muitos erros?" in avisos
    # As marcas do aviso viram negrito e link, sem sobrar asterisco ou colchete na tela
    assert "**" not in avisos and "](" not in avisos
    assert pagina.locator("#res-warnings-list strong", has_text="Muitos erros?").count() == 1
    link = pagina.locator("#res-warnings-list a")
    assert link.inner_text() == "PDF24"
    assert link.get_attribute("href") == "https://tools.pdf24.org/pt/ocr-pdf"
    assert link.get_attribute("rel") == "noopener noreferrer"

    # O campo fica no painel de opções, fechado: muda o valor como a pessoa faria ao sair dele
    pagina.evaluate(
        "() => { const c = document.getElementById('opt-max-kb'); c.value = '20';"
        " c.dispatchEvent(new Event('change')); }"
    )
    pagina.locator("#toast-message", has_text="Convertido de novo").wait_for(timeout=PRAZO_CONVERSAO_MS)
    assert "padronizacao dos relatorios mensais" in pagina.evaluate("() => currentResultFiles[0].conteudo")

    assert erros == []


@pytest.mark.parametrize(
    ("worker", "mensagem"),
    [
        # O worker original, sem os recursos que completam o navegador
        ("vendor/pdfjs-{versao}/pdf.worker.min.js", "O leitor de PDF parou com um erro"),
        # Um arquivo que não carrega: a orientação é a conexão, e não o navegador
        ("nao-existe.js", "Não foi possível carregar o leitor de PDF"),
    ],
    ids=["sem-recursos", "nao-carrega"],
)
def test_erro_no_worker_do_pdfjs_aparece_na_tela(contexto: object, endereco: str, worker: str, mensagem: str) -> None:
    """Um erro dentro do worker do PDF.js não rejeita a promessa do PDF.js: sem a página
    ouvir o worker, o OCR ficava parado em "Abrindo o PDF..." até a pessoa desistir. Aqui
    o worker falha, e o erro tem de chegar à tela, com a orientação certa."""
    app = (DOCS / "app.js").read_text(encoding="utf-8")
    versao = re.search(r"const VERSAO_PDFJS = '([^']+)'", app)
    assert versao, "VERSAO_PDFJS não encontrada em app.js"
    pagina = contexto.new_page()  # type: ignore[attr-defined]
    pagina.add_init_script(_sem_recursos_novos(worker.format(versao=versao.group(1))))

    pagina.set_viewport_size({"width": 794, "height": 1123})
    pagina.set_content(PAGINA_DIGITALIZADA)
    jpeg = pagina.screenshot(type="jpeg", quality=90)
    pdf = _pdf_de_imagem(jpeg, 794, 1123)

    pagina.goto(endereco)
    _esperar_conversor(pagina)
    pagina.set_input_files(
        "#file-input", files=[{"name": "digitalizado.pdf", "mimeType": "application/pdf", "buffer": pdf}]
    )
    pagina.locator("#status-ocr-iniciar").wait_for(state="visible", timeout=PRAZO_CONVERSAO_MS)
    pagina.click("#status-ocr-iniciar")
    # Bem antes do prazo do OCR: o erro vem assim que o PDF.js pede algo ao worker
    pagina.locator("#pyodide-status-card", has_text=mensagem).wait_for(timeout=PRAZO_CONVERSAO_MS)
    assert "Não foi possível reconhecer o texto" in pagina.locator("#pyodide-status-card").inner_text()
