"""Numeração do SEI como o navegador a mostra, conferida por captura de tela.

O navegador não entrega ao JavaScript o valor de um contador CSS: o ::before de um
Item_Nivel2 devolve "counter(item-n1) ..." e não "2.1.". Por isso a conferência é pela
imagem. A página gerada pelo conversor é comparada com uma referência que tem o mesmo
conteúdo e o mesmo CSS, e que só muda onde nascem os contadores iniciais: num div vazio,
irmão dos parágrafos, arranjo que numera certo no Chromium e no WebKit. As duas imagens
precisam ser iguais. Se a página gerada voltar a declarar os contadores no body (ou no
html), o Chromium emenda os subitens (2.3 logo depois de "2.") e as imagens divergem.

Fica na marca e2e, como o teste da página: precisa dos navegadores do Playwright.
"""
from __future__ import annotations

import re

import pytest

from conversorsei.montagem import COUNTER_RESET_INICIAL, montar_html

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e

# Duas seções com subitens, incisos, alíneas e parágrafos numerados: cada Item_Nivel1
# precisa recomeçar os subitens, e cada Item_Nivel2 os incisos
CORPO = "\n".join(
    f'<p class="{classe}">{texto}</p>'
    for classe, texto in (
        ("Item_Nivel1", "Primeira seção"),
        ("Item_Nivel2", "Subitem"),
        ("Item_Nivel3", "Subitem de terceiro nível"),
        ("Item_Nivel4", "Subitem de quarto nível"),
        ("Item_Nivel2", "Outro subitem"),
        ("Item_Inciso_Romano", "Inciso"),
        ("Item_Alinea_Letra", "Alínea"),
        ("Item_Alinea_Letra", "Outra alínea"),
        ("Item_Inciso_Romano", "Outro inciso"),
        ("Item_Nivel1", "Segunda seção"),
        ("Item_Nivel2", "Subitem que recomeça"),
        ("Paragrafo_Numerado_Nivel1", "Parágrafo numerado"),
        ("Paragrafo_Numerado_Nivel2", "Parágrafo numerado de segundo nível"),
        ("Item_Nivel1", "Terceira seção"),
        ("Item_Nivel2", "Subitem que recomeça de novo"),
    )
)

RE_REGRA_CSS = re.compile(r"([^{}]+)\{([^{}]*)\}")
RE_COUNTER_RESET = re.compile(r"counter-reset:[^;}]*;?")


def referencia(html: str) -> str:
    """A mesma página, com os contadores iniciais num div vazio no começo do body.

    Tira o counter-reset de toda regra que não seja de parágrafo: no CSS do SEI, só as
    classes de parágrafo zeram contadores, e o que sobra é a declaração inicial da página,
    onde quer que ela esteja (body, html, body::before).
    """

    def sem_reset_fora_de_paragrafo(regra: re.Match[str]) -> str:
        seletor, declaracoes = regra.group(1), regra.group(2)
        if seletor.strip().startswith("p."):
            return regra.group(0)
        return f"{seletor}{{{RE_COUNTER_RESET.sub('', declaracoes)}}}"

    inicio, fim = html.index("<style>"), html.index("</style>")
    estilo = RE_REGRA_CSS.sub(sem_reset_fora_de_paragrafo, html[inicio:fim])
    div = f'<div style="counter-reset:{COUNTER_RESET_INICIAL}"></div>'
    return html[:inicio] + estilo + html[fim:].replace("<body>", f"<body>\n{div}", 1)


@pytest.fixture(params=["chromium", "webkit"])
def pagina(request: pytest.FixtureRequest):
    with sync_api.sync_playwright() as p:
        navegador = getattr(p, request.param).launch()
        yield navegador.new_page(viewport={"width": 800, "height": 600})
        navegador.close()


def captura(pagina, html: str) -> bytes:
    pagina.set_content(html)
    return pagina.screenshot(full_page=True)


def test_numeracao_exibida_igual_a_da_referencia(pagina):
    gerada = montar_html(CORPO)
    assert captura(pagina, gerada) == captura(pagina, referencia(gerada)), (
        "A numeração exibida diverge da referência. Os contadores iniciais precisam nascer "
        "num irmão dos parágrafos (body::before), e não no body ou no html."
    )
