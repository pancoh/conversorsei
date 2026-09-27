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


def _enviar(pagina: object) -> None:
    pagina.set_input_files(  # type: ignore[attr-defined]
        "#file-input", files=[{"name": "nota.md", "mimeType": "text/markdown", "buffer": NOTA}]
    )


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

    copiado = _copiar(pagina)
    assert "NOTA TÉCNICA" in copiado
    assert 'class="Item_Nivel1"' in copiado

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
    _enviar(pagina)
    pagina.locator("#status-relato").wait_for(state="hidden", timeout=PRAZO_CONVERSAO_MS)

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
