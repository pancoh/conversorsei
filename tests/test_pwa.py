"""Coerência do aplicativo instalável (manifest, service worker e ícones).

Estes testes não abrem um navegador: eles travam os erros que fazem a página parar de
funcionar sem rede e que passariam despercebidos numa revisão, como uma lista de
pré-cache citando um arquivo que foi renomeado.
"""
from __future__ import annotations

import json
import re
import struct
import zipfile
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SW = DOCS / "sw.js"
MANIFEST = DOCS / "manifest.webmanifest"
INDEX = DOCS / "index.html"
APP = DOCS / "app.js"


def _lista_js(fonte: str, nome_da_const: str) -> list[str]:
    """Extrai os literais de string de um array declarado no JavaScript."""
    m = re.search(rf"const {nome_da_const} = \[(.*?)\];", fonte, re.DOTALL)
    assert m, f"{nome_da_const} não encontrada em sw.js"
    return re.findall(r"'([^']+)'", m.group(1))


def test_precache_lista_apenas_arquivos_existentes():
    """Um arquivo renomeado sem atualizar a lista quebraria a abertura sem rede."""
    for referencia in _lista_js(SW.read_text(encoding="utf-8"), "ARQUIVOS_ESSENCIAIS"):
        if referencia == "./":
            continue
        caminho = DOCS / referencia[2:]
        assert caminho.is_file(), f"{referencia} está no pré-cache mas não existe em docs/"


def test_manifest_valido_e_com_icones_no_tamanho_declarado():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["start_url"] == "."
    assert manifest["display"] == "standalone"
    assert manifest["lang"] == "pt-BR"
    # O ícone mascarável é o que o Android usa para recortar no formato do sistema
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"])

    for icone in manifest["icons"]:
        caminho = DOCS / icone["src"]
        assert caminho.is_file(), f"ícone ausente: {icone['src']}"

        # Confere o tamanho real no cabeçalho IHDR do PNG, e não só o nome do arquivo
        cabecalho = caminho.read_bytes()[:26]
        assert cabecalho[:8] == b"\x89PNG\r\n\x1a\n", f"{icone['src']} não é PNG"
        largura, altura = struct.unpack(">II", cabecalho[16:24])
        declarado = int(icone["sizes"].split("x")[0])
        assert (largura, altura) == (declarado, declarado), (
            f"{icone['src']} tem {largura}x{altura}, mas o manifest declara {icone['sizes']}"
        )


def test_index_liga_o_manifest_e_o_app_registra_o_service_worker():
    index = INDEX.read_text(encoding="utf-8")
    assert '<link rel="manifest" href="manifest.webmanifest">' in index
    assert '<meta name="theme-color"' in index

    app = APP.read_text(encoding="utf-8")
    assert "navigator.serviceWorker.register('./sw.js')" in app
    # Sem a checagem de protocolo, abrir o arquivo do disco imprimiria um erro no console
    assert "location.protocol" in app


def test_download_do_bundle_nao_usa_sufixo_de_versao_na_url():
    """Regressão: "conversorsei.zip?v=" + Date.now() derruba a conversão sem rede.

    Cada carregamento pediria um endereço novo, que o service worker nunca tem guardado,
    e o motor falharia com "Failed to fetch" logo na inicialização.
    """
    app = APP.read_text(encoding="utf-8")
    m = re.search(r"fetch\('conversorsei\.zip([^']*)'", app)
    assert m, "o download do bundle mudou de forma; confira se ainda funciona sem rede"
    assert m.group(1) == "", "a URL do bundle não pode carregar sufixo de versão"


def test_wheels_locais_e_pyodide_externo():
    """O primeiro acesso não depende do PyPI para instalar pacotes Python puros."""
    sw = SW.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" in sw
    assert "cdn.jsdelivr.net" in INDEX.read_text(encoding="utf-8")
    assert "files.pythonhosted.org" not in sw
    assert "pypi.org" not in sw
    app = APP.read_text(encoding="utf-8")
    for nome in (
        "typing_extensions-4.16.0-py3-none-any.whl",
        "python_docx-1.2.0-py3-none-any.whl",
        "pypdf-6.16.1-py3-none-any.whl",
    ):
        assert nome in sw and nome in app
        assert zipfile.is_zipfile(DOCS / "vendor" / nome)


def test_pagina_app_e_pacote_vem_da_rede_antes_do_cache():
    """Regressão: servidos do cache e atualizados em segundo plano, a página nova rodava
    com o app.js antigo por várias visitas depois do deploy.

    Página, app.js e pacote vêm da rede, confirmados com o servidor (e não com o cache
    HTTP), e o pré-cache também pula o cache HTTP. Só a pasta vendor, com a versão no
    nome do arquivo, continua servida do cache.
    """
    sw = SW.read_text(encoding="utf-8")
    assert "redePrimeiro(requisicao, './index.html')" in sw
    assert "versionado ? cacheERevalida(requisicao) : redePrimeiro(requisicao)" in sw
    assert "cache: 'no-cache'" in sw
    assert "new Request(url, { cache: 'reload' })" in sw


def test_busca_no_cache_ignora_a_query_string():
    """Sem ignoreSearch, qualquer "?v=" numa URL vira um endereço desconhecido sem rede."""
    assert "ignoreSearch: true" in SW.read_text(encoding="utf-8")


def test_contador_de_acessos_fica_fora_do_cache_e_nao_recebe_o_nome_do_arquivo():
    """O GoatCounter conta visitas e conversões. Ele não entra no cache do service worker
    (sem rede, a visita só deixa de ser contada) e o evento de conversão leva a extensão,
    nunca o nome do arquivo, que pode identificar o processo."""
    index = INDEX.read_text(encoding="utf-8")
    assert 'data-goatcounter="https://conversorsei.goatcounter.com/count"' in index
    assert 'src="https://gc.zgo.at/count.js"' in index

    sw = SW.read_text(encoding="utf-8")
    externas = _lista_js(sw, "ORIGENS_EXTERNAS")
    assert "gc.zgo.at" not in externas
    assert not any("goatcounter" in origem for origem in externas)

    app = APP.read_text(encoding="utf-8")
    m = re.search(r"window\.goatcounter\.count\(\{(.*?)\}\)", app, re.DOTALL)
    assert m, "o evento de conversão mudou de forma; confira o que ele envia"
    assert "nomeArquivo" not in m.group(1)


def test_ativacao_apaga_so_os_proprios_caches():
    """Regressão: a ativação apagava todo cache do domínio, que é compartilhado com outros
    sites e com o endereço antigo da própria página."""
    sw = SW.read_text(encoding="utf-8")
    assert "const PREFIXO_CACHE = 'conversao-sei-';" in sw
    assert "n.startsWith(PREFIXO_CACHE) && !atuais.includes(n)" in sw
    assert "`conversao-sei-estatico-${VERSAO}`" in sw and "`conversao-sei-execucao-${VERSAO}`" in sw


def test_mensagem_do_pdf_sem_texto_oferece_o_ocr():
    """A página mostra o botão do OCR quando a mensagem de erro traz a marca do PDF sem
    camada de texto. Se a frase do pdf_converter mudar, o botão some sem aviso."""
    app = APP.read_text(encoding="utf-8")
    m = re.search(r"const MARCA_PDF_SEM_TEXTO = '([^']+)'", app)
    assert m, "MARCA_PDF_SEM_TEXTO não encontrada em app.js"
    fonte = (DOCS.parent / "conversorsei" / "pdf_converter.py").read_text(encoding="utf-8")
    assert m.group(1) in fonte


def test_worker_do_pdfjs_e_da_mesma_versao_que_a_pagina():
    """O worker do PDF.js vem de um arquivo de entrada com a versão no nome, que o importa
    da pasta com a mesma versão. Página e worker de versões diferentes se recusam a
    trabalhar juntos, e o erro só apareceria na hora do OCR."""
    app = APP.read_text(encoding="utf-8")
    m = re.search(r"const VERSAO_PDFJS = '([^']+)'", app)
    assert m, "VERSAO_PDFJS não encontrada em app.js"
    versao = m.group(1)
    assert "const PASTA_PDFJS = `vendor/pdfjs-${VERSAO_PDFJS}/`;" in app
    assert "pdfjsWorker: `pdfjs-worker-${VERSAO_PDFJS}.js`," in app
    pasta = DOCS / "vendor" / f"pdfjs-{versao}"
    assert (pasta / "pdf.min.js").is_file() and (pasta / "pdf.worker.min.js").is_file()
    worker = (DOCS / f"pdfjs-worker-{versao}.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import '([^']+)';", worker, flags=re.M)
    assert imports == ["./pdfjs-compativel.js", f"./vendor/pdfjs-{versao}/pdf.worker.min.js"]


def test_entradas_antigas_do_worker_do_pdfjs_apontam_para_pastas_publicadas():
    """Os arquivos de entrada de versões anteriores ficam para abas abertas antes de uma
    troca. Cada um tem de importar um worker que ainda está no site."""
    for entrada in DOCS.glob("pdfjs-worker*.js"):
        texto = entrada.read_text(encoding="utf-8")
        for caminho in re.findall(r"^import '\./([^']+)';", texto, flags=re.M):
            assert (DOCS / caminho).is_file(), f"{entrada.name} importa {caminho}, que não existe"
