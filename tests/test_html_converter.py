"""Testes do leitor de HTML.

O caso que mais pesa é a volta: a saída do conversor, convertida de novo, precisa sair
igual. É o que garante que o HTML do SEI, que traz as mesmas classes, chegue inteiro.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conversorsei.cli import arquivos_observaveis
from conversorsei.core import converter_diretorio, converter_documento, entra_na_varredura
from conversorsei.entrada import StreamNomeado
from conversorsei.html_converter import decodificar_html, extrair_markdown_html
from conversorsei.web import converter_documento_memoria
from tests.test_classes_sei import montar_docx_todas_as_classes

RAIZ = Path(__file__).resolve().parent.parent


def _corpo(conteudo: str) -> str:
    """O que vai para o SEI: tudo depois do comentário de instruções do <body>."""
    return conteudo.split("<body>", 1)[1].split("-->", 1)[1]


def _converter(html: str | bytes, nome: str = "pagina.html") -> dict:
    dados = html.encode("utf-8") if isinstance(html, str) else html
    res = converter_documento_memoria(nome_arquivo=nome, conteudo_bytes=dados)
    assert res["sucesso"] is True, res["erros"]
    return res


def _markdown(html: str, avisos: list[str] | None = None) -> str:
    return extrair_markdown_html(StreamNomeado(html.encode("utf-8"), "pagina.html"), avisos)


@pytest.mark.parametrize(
    "nome,origem",
    [
        ("todas_as_classes.docx", montar_docx_todas_as_classes),
        ("exemplo_completo.md", lambda: (RAIZ / "exemplos" / "exemplo_completo.md").read_bytes()),
        ("nota_tecnica_exemplo.md", lambda: (RAIZ / "exemplos" / "nota_tecnica_exemplo.md").read_bytes()),
    ],
)
def test_saida_do_conversor_volta_igual(nome, origem):
    """As 34 classes, listas, tabelas, links, código e assinatura atravessam a volta."""
    ida = _converter(origem(), nome)["arquivos"][0]["conteudo"]
    volta = _converter(ida, "volta.html")
    assert _corpo(volta["arquivos"][0]["conteudo"]) == _corpo(ida)
    assert volta["avisos"] == []


def test_html_simples_sem_fechamentos_vira_markdown():
    markdown = _markdown(
        """<h1>Nota de teste</h1>
        <p>Texto com <b>negrito </b>e <i>itálico</i>, asterisco * e <a href="https://gov.br/a b">link</a>.
        <p>Segundo parágrafo
        <ul><li>um<li>dois<ul><li>dois.a</ul><li><p>três</p></ul>
        <blockquote><p>Art. 1º Citado.</p></blockquote>
        <pre>def f():
            return 1</pre>"""
    )
    assert markdown.splitlines() == [
        "# Nota de teste",
        "",
        r"Texto com **negrito** e *itálico*, asterisco \* e [link](https://gov.br/a%20b).",
        "",
        "Segundo parágrafo",
        "",
        "- um",
        "- dois",
        "  - dois.a",
        "- três",
        "",
        '<p class="Citação">Art. 1º Citado.</p>',
        "",
        "```",
        "def f():",
        "            return 1",
        "```",
    ]


def test_script_estilo_e_titulo_da_pagina_nao_entram():
    res = _converter(
        "<html><head><title>Aba</title><style>p{color:red}</style></head>"
        "<body><script>alert('x')</script><p onclick=\"roubar()\">Texto.</p></body></html>"
    )
    corpo = _corpo(res["arquivos"][0]["conteudo"])
    assert "Texto." in corpo
    for resto in ("Aba", "color:red", "alert", "roubar"):
        assert resto not in corpo


def test_classe_do_sei_no_paragrafo_e_na_celula_e_respeitada():
    res = _converter(
        '<p class="Item_Nivel1">ASSUNTO</p><p class="Texto_Ementa">Ementa.</p>'
        "<table><tr><td>Coluna</td><td>Valor</td></tr>"
        '<tr><td><p class="Tabela_Texto_Centralizado">Sim</p></td><td align="right">12,5</td></tr></table>'
    )
    corpo = _corpo(res["arquivos"][0]["conteudo"])
    assert '<p class="Item_Nivel1">ASSUNTO</p>' in corpo
    assert '<p class="Texto_Ementa">Ementa.</p>' in corpo
    assert '<p class="Tabela_Texto_Centralizado">Sim</p>' in corpo
    assert '<p class="Tabela_Texto_Alinhado_Direita">12,5</p>' in corpo


def test_centralizado_em_caixa_alta_e_riscado_seguem_as_regras_de_formatacao():
    markdown = _markdown(
        '<p style="text-align: center"><strong>PORTARIA Nº 1</strong></p><p><s>Revogado.</s></p>'
    )
    assert '<p class="Texto_Centralizado_Maiusculas_Negrito">**PORTARIA Nº 1**</p>' in markdown
    assert '<p class="Tachado">Revogado.</p>' in markdown


def test_estilo_inline_vence_a_etiqueta():
    """O Google Docs embrulha o texto copiado num <b> com peso normal."""
    markdown = _markdown(
        '<b style="font-weight:normal" id="docs-internal-guid-1"><p>comum '
        '<span style="font-weight:700">forte</span></p></b>'
    )
    assert markdown.strip() == "comum **forte**"


def test_tabela_de_uma_celula_com_paragrafos_e_moldura():
    markdown = _markdown("<table><tr><td><p>Primeiro.</p><p>Segundo.</p></td></tr></table>")
    assert markdown.split() == ["Primeiro.", "Segundo."]


def test_assinatura_e_autenticidade_do_sei_saem_com_aviso():
    avisos: list[str] = []
    markdown = _markdown(
        "<p>Texto do documento.</p>"
        '<table><tr><td><img src="selo.png"></td><td><p>Documento assinado eletronicamente por '
        "Fulano, em 01/01/2026, com fundamento no Decreto nº 10.543.</p></td></tr></table>"
        "<p>A autenticidade deste documento pode ser conferida no site https://sei, informando o "
        "código verificador 123 e o código CRC ABC.</p>"
        "<p>Referência: Processo nº 00000.000000/2026-00 SEI nº 1234567</p>",
        avisos,
    )
    assert markdown.strip() == "Texto do documento."
    assert any("assinatura eletrônica" in aviso for aviso in avisos)
    assert any("Imagens" in aviso for aviso in avisos)


def test_referencia_no_corpo_do_texto_fica():
    """Só a linha de rodapé do SEI sai; a referência dentro de uma frase é texto."""
    markdown = _markdown("<p>Referência: Processo nº 00000.000000/2026-00, conforme despacho.</p>")
    assert "conforme despacho" in markdown


def test_codificacao_declarada_e_lida():
    pagina = '<html><head><meta charset="windows-1252"></head><body><p>Ação é válida.</p></body></html>'
    assert "Ação é válida." in decodificar_html(pagina.encode("cp1252"))
    latin1 = '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><p>Não</p>'
    assert "Não" in decodificar_html(latin1.encode("cp1252"))


def test_codificacao_sem_declaracao_segue_a_leitura_do_txt():
    assert "Ação" in decodificar_html("<p>Ação</p>".encode())
    assert "Ação" in decodificar_html("<p>Ação</p>".encode("cp1252"))


def test_html_do_word_avisa_para_usar_o_docx():
    avisos: list[str] = []
    _markdown(
        '<html xmlns:w="urn:schemas-microsoft-com:office:word"><body><p class=MsoNormal>Texto.</p></body></html>',
        avisos,
    )
    assert any(".docx" in aviso for aviso in avisos)


def test_html_sem_texto_falha_com_mensagem():
    res = converter_documento_memoria(nome_arquivo="vazia.html", conteudo_bytes=b"<html><body><img src=x></body>")
    assert res["sucesso"] is False
    assert "vazia.html" in res["erros"][0]


def test_web_e_cli_geram_o_mesmo_html(tmp_path):
    origem = tmp_path / "pagina.html"
    origem.write_text("<h2>1. ASSUNTO</h2><p>1.1. Texto do documento.</p>", encoding="utf-8")

    res_disco = converter_documento(origem, outdir=tmp_path / "saida")
    assert res_disco.sucesso, res_disco.erros
    res_memoria = _converter(origem.read_bytes(), origem.name)

    assert [p.name for p in res_disco.arquivos_gerados] == [a["nome"] for a in res_memoria["arquivos"]]
    assert res_disco.arquivos_gerados[0].read_text(encoding="utf-8") == res_memoria["arquivos"][0]["conteudo"]


def test_varredura_nao_converte_a_propria_saida(tmp_path):
    """Sem -o, a saída fica na pasta da entrada, e a segunda volta a converteria."""
    (tmp_path / "pagina.html").write_text("<p>Texto.</p>", encoding="utf-8")
    (tmp_path / "nota.md").write_text("Texto.", encoding="utf-8")

    for _ in range(2):
        resultados = converter_diretorio(tmp_path)
        assert sorted(r.arquivo_origem.name for r in resultados) == ["nota.md", "pagina.html"]
    assert sorted(p.name for p in tmp_path.glob("*.html")) == ["nota_SEI.html", "pagina.html", "pagina_SEI.html"]
    observados = arquivos_observaveis([str(tmp_path)], recursivo=False)
    assert sorted(p.name for p in observados) == ["nota.md", "pagina.html"]


@pytest.mark.parametrize(
    "nome",
    ["nota_SEI.html", "nota_SEI_parte02.html", "nota_SEI_corpo.html", "nota_SEI_corpo_parte01.html",
     "Nota_Tecnica_SEI_12.html", "Nota_Tecnica_SEI_12_parte03.html"],
)
def test_nomes_da_saida_ficam_fora_da_varredura(tmp_path, nome):
    arquivo = tmp_path / nome
    arquivo.write_text("<p>Texto.</p>", encoding="utf-8")
    assert not entra_na_varredura(arquivo)


def test_saida_com_nome_escolhido_fica_fora_da_varredura_pelo_titulo(tmp_path):
    origem = tmp_path / "pagina.md"
    origem.write_text("Texto.", encoding="utf-8")
    converter_documento(origem, caminho_saida=tmp_path / "entrega.html")
    assert not entra_na_varredura(tmp_path / "entrega.html")
    assert entra_na_varredura(origem)


def test_saida_pedida_pelo_nome_ainda_e_convertida(tmp_path):
    saida = tmp_path / "nota_SEI.html"
    saida.write_text('<p class="Item_Nivel1">ASSUNTO</p>', encoding="utf-8")
    res = converter_documento(saida, outdir=tmp_path / "outra")
    assert res.sucesso, res.erros


def test_texto_colado_do_word_nao_pede_o_docx():
    """Colado, o HTML do Word traz a formatação no texto: o aviso de arquivo não vale."""
    pagina = '<html xmlns:w="urn:schemas-microsoft-com:office:word"><body><p class=MsoNormal>Texto.</p></body></html>'
    res = converter_documento_memoria(nome_arquivo="texto_colado.html", conteudo_bytes=pagina.encode(), colado=True)
    assert res["sucesso"] is True, res["erros"]
    assert res["avisos"] == []


def test_copia_do_google_docs_nao_recebe_o_aviso_da_exportacao():
    """A cópia (docs-internal-guid) traz a ênfase no style, que é lido."""
    avisos: list[str] = []
    _markdown('<b id="docs-internal-guid-1" style="font-weight:normal"><p>Texto.</p></b>', avisos)
    assert avisos == []


def test_colado_sem_texto_explica_sem_citar_arquivo():
    res = converter_documento_memoria(
        nome_arquivo="texto_colado.html", conteudo_bytes=b'<img src="x.png">', colado=True
    )
    assert res["sucesso"] is False
    assert "conteúdo colado" in res["erros"][0]


# Lista numerada: o número fica escrito no texto, sem marcador e fora da numeração do SEI
RE_P = re.compile(r'<(p|li) class="([^"]+)">(.*?)</(?:p|li)>', re.DOTALL)


def _paragrafos(html: str, **opcoes) -> list[tuple[str, str, str]]:
    res = converter_documento_memoria("texto_colado.html", html.encode(), so_corpo=True, colado=True, **opcoes)
    assert res["sucesso"], res["erros"]
    return RE_P.findall(res["arquivos"][0]["conteudo"])


def test_lista_numerada_sai_com_o_numero_no_texto():
    html = (
        "<p>Solicitamos as seguintes informações:</p>"
        "<ol><li><p>O Ministério possui setor responsável?</p>"
        '<ol type="a"><li>Em caso afirmativo, informe.</li><li>Em caso negativo, informe.</li></ol></li>'
        "<li>Quais são as atribuições?</li></ol>"
        '<ol start="3"><li>Qual é a equipe?</li></ol>'
        '<ol style="list-style-type: upper-roman"><li>Inciso um.</li><li>Inciso dois.</li></ol>'
        "<ul><li>Marcador continua marcador.</li></ul>"
    )
    paragrafos = _paragrafos(html)
    textos = [t for _, _, t in paragrafos]
    assert textos[1:8] == [
        "1. O Ministério possui setor responsável?",
        "a) Em caso afirmativo, informe.",
        "b) Em caso negativo, informe.",
        "2. Quais são as atribuições?",
        "3. Qual é a equipe?",
        "I - Inciso um.",
        "II - Inciso dois.",
    ]
    # Nem marcador nem Item_Nivel: o "1." é texto, e o documento não ganha numeração
    assert {c for _, c, _ in paragrafos[1:8]} == {"Texto_Justificado"}
    assert paragrafos[8][0] == "li"


def test_lista_numerada_dentro_da_citacao_entre_aspas():
    html = (
        '<p>"Pedido transcrito:</p>'
        "<ol><li>O Ministério possui setor responsável?</li><li>Quais são as atribuições?</li></ol>"
        '<p>Fim do pedido."</p><p>Resposta da unidade.</p>'
    )
    paragrafos = _paragrafos(html, citacao_por_recuo=True)
    assert [(c, t) for _, c, t in paragrafos] == [
        ("Citação", '"Pedido transcrito:'),
        ("Citação", "1. O Ministério possui setor responsável?"),
        ("Citação", "2. Quais são as atribuições?"),
        ("Citação", 'Fim do pedido."'),
        ("Texto_Justificado", "Resposta da unidade."),
    ]


@pytest.mark.parametrize(
    "posicao, tipo, esperado",
    [(1, "1", "1."), (12, "1", "12."), (2, "a", "b)"), (27, "a", "aa)"), (3, "A", "C)"), (4, "I", "IV -"), (9, "i", "ix -")],
)
def test_numero_do_item(posicao, tipo, esperado):
    from conversorsei.html_converter import numero_do_item

    assert numero_do_item(posicao, tipo) == esperado


def test_html_link_com_esquema_inseguro_fica_so_o_texto():
    """A conferência do esquema não depende da caixa: "JavaScript:" também fica de fora."""
    markdown = _markdown(
        '<p><a href="JavaScript:alert(1)">um</a> <a href="data:text/html,x">dois</a> '
        '<a href="mailto:sei@gov.br">três</a></p>'
    )
    assert markdown.strip() == "um dois [três](mailto:sei@gov.br)"


def test_barra_vertical_na_celula_nao_cria_coluna():
    res = _converter('<table><tr><td>A | B</td><td>C</td></tr></table>')
    corpo = _corpo(res['arquivos'][0]['conteudo'])
    assert corpo.count('<td ') == 2
    assert '>A | B<' in corpo
    assert '>C<' in corpo


@pytest.mark.parametrize('texto', [r'C:\dados\(2026)', r'Regex: \d+\.', r'Literal: \* e \\ e \[texto]'])
def test_html_preserva_barras_invertidas_literais(texto):
    corpo = _corpo(_converter(f'<p>{texto}</p>')['arquivos'][0]['conteudo'])
    assert texto in corpo


@pytest.mark.parametrize('html,esperado', [
    ('<strong><a href="https://exemplo.org">Texto</a></strong>', '<strong>Texto</strong>'),
    ('<a href="https://exemplo.org"><strong>Texto</strong></a>', '<strong>Texto</strong>'),
    ('<em><a href="https://exemplo.org">Texto</a></em>', '<em>Texto</em>'),
    ('<a href="https://exemplo.org">Antes <strong>Texto</strong> depois</a>', 'Antes <strong>Texto</strong> depois'),
    ('<strong><a href="https://exemplo.org"><em>Texto</em></a></strong>', '<strong><em>Texto</em></strong>'),
])
def test_enfase_do_link_atravessa_a_conversao(html, esperado):
    corpo = _corpo(_converter(f'<p>{html}</p>')['arquivos'][0]['conteudo'])
    assert f'<a href="https://exemplo.org">{esperado}</a>' in corpo
    assert '**' not in corpo


def test_larguras_da_tabela_e_colunas_sobrevivem_a_reconversao():
    from conversorsei.core import converter_bytes

    html = '<table width="50%"><tr><td width="20%">A</td><td width="80%">B</td></tr><tr><td>C</td><td>D</td></tr></table>'
    ida = converter_bytes('tabela.html', html.encode(), so_corpo=True)
    corpo = ida.arquivos[0].conteudo
    assert 'width="50%"' in corpo
    assert 'width="20.0%"' in corpo and 'width="80.0%"' in corpo
    volta = converter_bytes('volta.html', corpo.encode(), so_corpo=True)
    assert volta.arquivos[0].conteudo == corpo


def test_colunas_iguais_explicitas_nao_sao_recalculadas():
    html = '<table><tr><td width="50%">1</td><td width="50%">Texto muito mais longo</td></tr></table>'
    corpo = _corpo(_converter(html)['arquivos'][0]['conteudo'])
    assert corpo.count('width="50.0%"') == 2


def test_codigo_html_com_crases_internas_mantem_o_bloco_inteiro():
    texto = 'primeira\n```\nultima\n````'
    ida = _converter(f'<pre>{texto}</pre>')
    corpo = _corpo(ida['arquivos'][0]['conteudo'])
    assert '<p class="Texto_Mono_Espaçado">primeira<br />```<br />ultima<br />````</p>' in corpo
    volta = _converter(ida['arquivos'][0]['conteudo'])
    assert _corpo(volta['arquivos'][0]['conteudo']) == corpo
