"""Testes do leitor de ODT.

Os arquivos de teste são montados à mão, com a estrutura que o LibreOffice grava. Não
dá para depender do LibreOffice no CI, e o formato é estável o bastante para ser escrito
diretamente.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from conversorsei.core import converter_documento
from conversorsei.odt_converter import extrair_markdown_odt


def _odt_com_estilos_nomeados(tmp_path, automaticos, corpo, nomeados):
    namespaces = (
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
        'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
    )
    content = (
        f'<office:document-content {namespaces}><office:automatic-styles>{automaticos}'
        f'</office:automatic-styles><office:body><office:text>{corpo}</office:text>'
        '</office:body></office:document-content>'
    )
    styles = f'<office:document-styles {namespaces}><office:styles>{nomeados}</office:styles></office:document-styles>'
    caminho = tmp_path / 'estilos.odt'
    with zipfile.ZipFile(caminho, 'w') as z:
        z.writestr('mimetype', 'application/vnd.oasis.opendocument.text')
        z.writestr('content.xml', content)
        z.writestr('styles.xml', styles)
    return caminho


def test_odt_le_estilo_de_caractere_nomeado_e_heranca_com_valor_normal(tmp_path):
    caminho = _odt_com_estilos_nomeados(
        tmp_path,
        '<style:style style:name="T1" style:family="text" style:parent-style-name="Destaque">'
        '<style:text-properties fo:font-style="normal"/></style:style>',
        '<text:p><text:span text:style-name="Destaque">Ênfase nomeada</text:span> '
        '<text:span text:style-name="T1">Só negrito</text:span></text:p>',
        '<style:style style:name="Destaque" style:family="text" style:parent-style-name="Base">'
        '<style:text-properties fo:font-style="italic"/></style:style>'
        '<style:style style:name="Base" style:family="text">'
        '<style:text-properties fo:font-weight="bold"/></style:style>',
    )
    from conversorsei.core import converter_bytes

    disco = converter_documento(caminho, outdir=tmp_path / 'saida', so_corpo=True)
    memoria = converter_bytes(caminho.name, caminho.read_bytes(), so_corpo=True)
    assert disco.sucesso and memoria.sucesso
    html = memoria.arquivos[0].conteudo
    assert '<strong><em>Ênfase nomeada</em></strong>' in html
    assert '<strong>Só negrito</strong>' in html
    assert disco.arquivos_gerados[0].read_text(encoding='utf-8') == html
    assert memoria.avisos == []


def test_odt_titulo_segue_estilo_nomeado_intermediario(tmp_path):
    caminho = _odt_com_estilos_nomeados(
        tmp_path,
        '<style:style style:name="P1" style:family="paragraph" style:parent-style-name="MinhaSecao"/>',
        '<text:p text:style-name="P1">Seção sem número</text:p>',
        '<style:style style:name="MinhaSecao" style:family="paragraph" style:parent-style-name="Heading_20_1"/>',
    )
    resultado = converter_documento(caminho, outdir=tmp_path / 'saida', so_corpo=True)
    assert resultado.sucesso
    assert '<p class="Item_Nivel1">' in resultado.arquivos_gerados[0].read_text(encoding='utf-8')


def test_odt_ciclo_de_estilos_nao_interrompe_conversao(tmp_path):
    caminho = _odt_com_estilos_nomeados(
        tmp_path, '', '<text:p><text:span text:style-name="A">Texto.</text:span></text:p>',
        '<style:style style:name="A" style:family="text" style:parent-style-name="B"/>'
        '<style:style style:name="B" style:family="text" style:parent-style-name="A"/>',
    )
    assert extrair_markdown_odt(caminho).strip() == 'Texto.'

CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
  xmlns:xlink="http://www.w3.org/1999/xlink">
 <office:automatic-styles>
  <style:style style:name="P1" style:family="paragraph" style:parent-style-name="Heading_20_1"/>
  <style:style style:name="P2" style:family="paragraph" style:parent-style-name="Text_20_body"/>
  <style:style style:name="T1" style:family="text">
   <style:text-properties fo:font-weight="bold"/>
  </style:style>
  <style:style style:name="T2" style:family="text">
   <style:text-properties fo:font-style="italic"/>
  </style:style>
 </office:automatic-styles>
 <office:body>
  <office:text>
   <text:p text:style-name="P1">1. ASSUNTO</text:p>
   <text:p text:style-name="P2">Trata-se de <text:span text:style-name="T1">analise</text:span> com <text:span text:style-name="T2">enfase</text:span> e <text:a xlink:href="https://www.gov.br/">link</text:a>.</text:p>
   <text:h text:outline-level="2">1.1. Detalhamento</text:h>
   <text:p text:style-name="P2">Asterisco * e colchete [Lei] nao viram marcacao.</text:p>
   <table:table>
    <table:table-row>
     <table:table-cell><text:p>Parametro</text:p></table:table-cell>
     <table:table-cell><text:p>Situacao</text:p></table:table-cell>
    </table:table-row>
    <table:table-row>
     <table:table-cell><text:p>Impacto</text:p></table:table-cell>
     <table:table-cell><text:p>Baixo</text:p></table:table-cell>
    </table:table-row>
   </table:table>
   <text:list>
    <text:list-item><text:p text:style-name="P2">Primeiro item</text:p></text:list-item>
    <text:list-item><text:p text:style-name="P2">Segundo item</text:p></text:list-item>
   </text:list>
  </office:text>
 </office:body>
</office:document-content>
"""

def _odt(tmp_path: Path, content: str = CONTENT_XML) -> Path:
    caminho = tmp_path / "documento.odt"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", content)
    return caminho


def test_odt_extrai_estrutura_completa(tmp_path):
    md = extrair_markdown_odt(_odt(tmp_path))

    # Título por herança de estilo: o LibreOffice grava <text:p> com estilo derivado
    assert "# 1. ASSUNTO" in md
    assert "## 1.1. Detalhamento" in md
    assert "**analise**" in md
    assert "*enfase*" in md
    assert "[link](https://www.gov.br/)" in md
    # A marcação que veio do documento é escapada para não virar formatação
    assert r"Asterisco \* e colchete \[Lei\]" in md
    assert "| Parametro | Situacao |" in md
    assert "| --- | --- |" in md
    # Itens de lista saem colados, senão viram listas separadas
    assert "- Primeiro item\n- Segundo item" in md


def test_odt_recusa_arquivo_que_nao_e_odt(tmp_path):
    falso = tmp_path / "falso.odt"
    falso.write_bytes(b"isto nao e um zip")
    with pytest.raises(RuntimeError, match="não é um ODT válido"):
        extrair_markdown_odt(falso)


def test_odt_sem_texto_avisa(tmp_path):
    vazio = _odt(
        tmp_path,
        CONTENT_XML[: CONTENT_XML.index("<office:body>")]
        + "<office:body><office:text></office:text></office:body></office:document-content>",
    )
    with pytest.raises(RuntimeError, match="Nenhum texto"):
        extrair_markdown_odt(vazio)


def test_odt_com_imagem_e_texto_avisa_omissao(tmp_path):
    conteudo = CONTENT_XML.replace(
        'xmlns:xlink="http://www.w3.org/1999/xlink"',
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"',
    ).replace(
        "Trata-se de ",
        '<draw:frame><draw:image xlink:href="Pictures/grafico.png"/></draw:frame>Trata-se de ',
    )
    entrada = _odt(tmp_path, conteudo)
    res = converter_documento(entrada, outdir=tmp_path / "saida")
    assert res.sucesso
    assert any("Imagens do ODT" in aviso for aviso in res.avisos)


def test_odt_preserva_quebra_manual_de_linha(tmp_path):
    conteudo = CONTENT_XML.replace(
        "Asterisco * e colchete [Lei] nao viram marcacao.",
        "Rua A, 1<text:line-break/>Brasília",
    )
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert "Rua A, 1<br" in html
    assert "Brasília" in html


def test_odt_preserva_texto_da_nota_de_rodape(tmp_path):
    nota = (
        '<text:note text:note-class="footnote"><text:note-citation>1</text:note-citation>'
        '<text:note-body><text:p>Fonte do dado.</text:p></text:note-body></text:note>'
    )
    conteudo = CONTENT_XML.replace("Trata-se de ", "Trata-se de " + nota)
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert "Fonte do dado." in html
    assert "Nota 1:" in html
    assert any("seção Notas" in aviso for aviso in res.avisos)


def test_odt_preserva_celula_mesclada_sem_gerar_celula_extra(tmp_path):
    tabela = (
        '<table:table><table:table-row>'
        '<table:table-cell table:number-columns-spanned="2"><text:p>Título</text:p></table:table-cell>'
        '<table:covered-table-cell/>'
        '</table:table-row><table:table-row>'
        '<table:table-cell><text:p>A</text:p></table:table-cell>'
        '<table:table-cell><text:p>B</text:p></table:table-cell>'
        '</table:table-row></table:table>'
    )
    inicio = CONTENT_XML.index("   <table:table>")
    fim = CONTENT_XML.index("   </table:table>", inicio) + len("   </table:table>")
    conteudo = CONTENT_XML[:inicio] + tabela + CONTENT_XML[fim:]
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert 'colspan="2"' in html
    assert "Título" in html


def test_odt_avisa_sobre_mesclagem_vertical_que_exige_conferencia(tmp_path):
    conteudo = CONTENT_XML.replace(
        "<table:table-cell><text:p>Parametro</text:p></table:table-cell>",
        '<table:table-cell table:number-rows-spanned="2"><text:p>Parametro</text:p></table:table-cell>',
    )
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    assert any("mescladas entre linhas" in aviso for aviso in res.avisos)


def test_conversao_ponta_a_ponta_pelo_core(tmp_path):
    """O ODT entra pelo mesmo caminho dos demais formatos e sai com classes do SEI."""
    entrada = _odt(tmp_path)

    res = converter_documento(entrada, outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")

    assert 'class="Item_Nivel1"' in html
    assert "ASSUNTO" in html
    assert "<table" in html
    assert "<strong>analise</strong>" in html


def test_odt_quebra_de_linha_em_link_nao_deixa_marca_interna(tmp_path):
    """A marca da quebra de linha vira <br> também dentro do link, e nunca vai à saída."""
    conteudo = CONTENT_XML.replace(
        "Asterisco * e colchete [Lei] nao viram marcacao.",
        '<text:a xlink:href="https://exemplo.gov.br">linha1<text:line-break/>linha2</text:a>',
    )
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert "" not in html
    assert re.search(r"linha1<br ?/?>linha2", html), html


def test_odt_cabecalho_com_barra_escapada_nao_ganha_coluna(tmp_path):
    """As colunas saem do XML: um "|" no texto do cabeçalho não conta como coluna."""
    conteudo = CONTENT_XML.replace("<text:p>Parametro</text:p>", "<text:p>Entrada | saída</text:p>")
    markdown = extrair_markdown_odt(_odt(tmp_path, conteudo))
    separador = next(linha for linha in markdown.splitlines() if linha.startswith("| ---"))
    assert separador.count("---") == 2


def test_barra_vertical_da_tabela_odt_atravessa_o_pipeline(tmp_path):
    conteudo = CONTENT_XML.replace('<text:p>Parametro</text:p>', '<text:p>Entrada | saída</text:p>')
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / 'saida')
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding='utf-8')
    assert html.count('<td ') == 4
    assert '>Entrada | saída<' in html


def test_odt_expande_celulas_e_linhas_repetidas(tmp_path):
    conteudo = CONTENT_XML.replace('<table:table-row>', '<table:table-row table:number-rows-repeated="2">', 1)
    conteudo = conteudo.replace('<table:table-cell><text:p>Parametro', '<table:table-cell table:number-columns-repeated="3"><text:p>Parametro', 1)
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / 'saida')
    assert res.sucesso, res.erros
    html = res.arquivos_gerados[0].read_text(encoding='utf-8')
    assert html.count('<tr>') == 3
    assert html.count('Parametro') == 6
    assert html.count('Situacao') == 2
    assert html.count('<td ') == 12


def test_odt_preserva_barra_invertida_antes_de_pontuacao(tmp_path):
    texto = r'C:\dados\(2026) e \d+\.'
    conteudo = CONTENT_XML.replace('Asterisco * e colchete [Lei] nao viram marcacao.', texto)
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / 'saida')
    assert res.sucesso, res.erros
    assert texto in res.arquivos_gerados[0].read_text(encoding='utf-8')


def _tabela_repetida(tmp_path: Path, linha_extra: str) -> tuple:
    tabela = (
        "<table:table><table:table-row>"
        "<table:table-cell><text:p>Nome</text:p></table:table-cell>"
        '<table:table-cell table:number-columns-repeated="1020"/>'
        f"</table:table-row>{linha_extra}</table:table>"
    )
    inicio = CONTENT_XML.index("   <table:table>")
    fim = CONTENT_XML.index("   </table:table>", inicio) + len("   </table:table>")
    res = converter_documento(_odt(tmp_path, CONTENT_XML[:inicio] + tabela + CONTENT_XML[fim:]), outdir=tmp_path / "s")
    assert res.sucesso, res.erros
    return res, res.arquivos_gerados[0].read_text(encoding="utf-8")


def test_odt_repeticao_vazia_no_fim_sai_da_tabela(tmp_path):
    """O LibreOffice completa a linha com uma célula vazia repetida até o fim da grade.

    Expandidas, as mil colunas do Calc e o milhão de linhas vazias travavam a conversão.
    """
    vazias = '<table:table-row table:number-rows-repeated="1000000"><table:table-cell/></table:table-row>'
    res, html = _tabela_repetida(tmp_path, vazias)
    assert html.count("<tr>") == 1
    assert html.count("<td ") == 1
    assert not any("repetição" in aviso for aviso in res.avisos)


def test_odt_repeticao_com_texto_tem_teto_e_aviso(tmp_path):
    from conversorsei.odt_converter import LIMITE_COLUNAS_REPETIDAS, LIMITE_LINHAS_REPETIDAS

    linhas = (
        '<table:table-row table:number-rows-repeated="1000000">'
        '<table:table-cell table:number-columns-repeated="500"><text:p>x</text:p></table:table-cell>'
        "</table:table-row>"
    )
    res, html = _tabela_repetida(tmp_path, linhas)
    assert html.count("<tr>") == LIMITE_LINHAS_REPETIDAS
    # O Markdown completa toda linha até a largura da maior
    assert html.count("<td ") == LIMITE_LINHAS_REPETIDAS * LIMITE_COLUNAS_REPETIDAS
    assert any("repetição foi cortada" in aviso for aviso in res.avisos)


def test_odt_atributo_de_tabela_invalido_nao_derruba_a_conversao(tmp_path):
    conteudo = CONTENT_XML.replace(
        "<table:table-cell><text:p>Parametro",
        '<table:table-cell table:number-columns-repeated="abc" table:number-rows-spanned="x"><text:p>Parametro',
        1,
    )
    res = converter_documento(_odt(tmp_path, conteudo), outdir=tmp_path / "saida")
    assert res.sucesso, res.erros
    assert "Parametro" in res.arquivos_gerados[0].read_text(encoding="utf-8")
