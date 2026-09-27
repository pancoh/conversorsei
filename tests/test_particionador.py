from pathlib import Path

from conversorsei.particionador import (
    css_institucional,
    derivar_caminho_saida,
    dividir_em_partes,
    limpar_saidas_antigas,
    montar_html,
    orcamento_corpo,
)


def test_css_institucional_carregado():
    css = css_institucional()
    assert "p.Item_Nivel1" in css
    assert "p.Texto_Justificado" in css
    assert "p.Tabela_Texto_Centralizado" in css


def test_montar_html_contem_estilos_e_resets():
    corpo = '<p class="Texto_Justificado">Teste</p>'
    html = montar_html(corpo)
    assert "<!DOCTYPE html>" in html
    assert "counter-reset:item-n1" in html
    assert corpo in html


def test_orcamento_corpo_calculo():
    orcamento_completo = orcamento_corpo(22, so_corpo=False)
    orcamento_apenas_corpo = orcamento_corpo(22, so_corpo=True)
    assert orcamento_apenas_corpo == 22_000
    assert orcamento_completo < 22_000
    assert orcamento_completo > 10_000


def test_dividir_em_partes_respeita_limite():
    # 5 blocos de ~4KB cada
    blocos = [f'<p class="Texto_Justificado">{"a" * 4000}</p>' for _ in range(5)]
    partes = dividir_em_partes(blocos, max_bytes=9000)
    assert len(partes) >= 2
    # Nenhum bloco foi perdido
    total_blocos = sum(len(p) for p in partes)
    assert total_blocos == 5


def test_limpar_saidas_antigas(tmp_path):
    saida = tmp_path / "documento_SEI.html"
    partes = [tmp_path / f"documento_SEI_parte{i:02d}.html" for i in range(1, 4)]
    saida.write_text("unico", encoding="utf-8")
    for p in partes:
        p.write_text("parte", encoding="utf-8")

    # Ao gerar partes, deve remover o arquivo único e partes antigas
    removidos = limpar_saidas_antigas(saida, gerar_partes=True)
    assert saida not in tmp_path.glob("*.html")
    assert len(removidos) >= 4


def test_derivar_caminho_saida():
    assert derivar_caminho_saida("doc.docx") == Path("doc_SEI.html")
    assert derivar_caminho_saida("Nota_Tecnica_NT_01.docx") == Path("Nota_Tecnica_SEI_NT_01.html")
    assert derivar_caminho_saida("Nota_Tecnica_Revisada_NT_02.docx") == Path("Nota_Tecnica_SEI_NT_02.html")
    assert derivar_caminho_saida("doc.docx", so_corpo=True) == Path("doc_SEI_corpo.html")


def test_avancar_contadores_acompanha_niveis():
    from conversorsei.particionador import avancar_contadores, contadores_zerados

    corpo = (
        '<p class="Item_Nivel1">A</p>'
        '<p class="Item_Nivel2">B</p>'
        '<p class="Item_Nivel2">C</p>'
        '<p class="Item_Nivel1">D</p>'
        '<p class="Item_Inciso_Romano">E</p>'
    )
    estado = avancar_contadores(contadores_zerados(), corpo)
    assert estado["item-n1"] == 2
    # O segundo Item_Nivel1 zera os subníveis
    assert estado["item-n2"] == 0
    assert estado["romano_maiusculo"] == 1


def test_montar_html_continua_numeracao_da_parte_anterior():
    html = montar_html('<p class="Item_Nivel1">Seção</p>', contadores={"item-n1": 13})
    assert "counter-reset:item-n1 13" in html


def test_partes_seguintes_continuam_a_numeracao(tmp_path):
    from conversorsei.core import converter_documento

    linhas = []
    for i in range(1, 40):
        linhas.append(f"# {i}. SECAO {i}")
        linhas.append("Texto de preenchimento. " * 40)
    entrada = tmp_path / "grande.md"
    entrada.write_text("\n\n".join(linhas), encoding="utf-8")

    res = converter_documento(entrada, outdir=tmp_path)
    assert len(res.arquivos_gerados) > 1

    primeira = res.arquivos_gerados[0].read_text(encoding="utf-8")
    segunda = res.arquivos_gerados[1].read_text(encoding="utf-8")
    assert "counter-reset:item-n1 0" in primeira
    # A parte 2 retoma a contagem de onde a parte 1 parou
    itens_na_primeira = primeira.count('class="Item_Nivel1"')
    assert f"counter-reset:item-n1 {itens_na_primeira}" in segunda


def _tabela_html(linhas_corpo: list[str], cabecalho: str | None = None) -> str:
    cab = cabecalho or (
        '    <tr>\n      <td style="background-color:#e6e6e6;">Item</td>\n'
        '      <td style="background-color:#e6e6e6;">Descrição</td>\n    </tr>'
    )
    return (
        '<table border="1" cellpadding="1" cellspacing="1" style="width:100%;">\n'
        "  <tbody>\n" + "\n".join([cab, *linhas_corpo]) + "\n  </tbody>\n</table>"
    )


def _linha(i: int, tamanho: int = 400) -> str:
    return f'    <tr>\n      <td>{i}</td>\n      <td>{"x" * tamanho}</td>\n    </tr>'


def test_dividir_tabela_repete_cabecalho_em_cada_parte():
    from conversorsei.particionador import dividir_tabela

    tabela = _tabela_html([_linha(i) for i in range(60)])
    assert len(tabela.encode("utf-8")) > 20_000

    partes = dividir_tabela(tabela, max_bytes=8000)
    assert len(partes) >= 3

    for parte in partes:
        assert parte.startswith("<table")
        assert parte.endswith("</table>")
        # A linha de cabeçalho reaparece em toda parte
        assert parte.count("Descrição") == 1
        assert len(parte.encode("utf-8")) <= 8000

    # Nenhuma linha do corpo se perdeu nem foi duplicada
    total = sum(parte.count("<tr>") - 1 for parte in partes)
    assert total == 60


def test_dividir_tabela_nao_parte_celula_mesclada():
    from conversorsei.particionador import dividir_tabela

    # Cada par de linhas é amarrado por um rowspan="2" iniciado na linha par
    corpo = []
    for i in range(0, 40, 2):
        corpo.append(
            f'    <tr>\n      <td rowspan="2">Grupo {i}</td>\n      <td>{"x" * 400}</td>\n    </tr>'
        )
        corpo.append(f'    <tr>\n      <td>{"y" * 400}</td>\n    </tr>')

    partes = dividir_tabela(_tabela_html(corpo), max_bytes=3000)
    assert len(partes) >= 2

    for parte in partes:
        # Um rowspan="2" só é válido se a linha seguinte estiver na mesma parte
        linhas = parte.split("<tr>")[2:]  # descarta o preâmbulo e a linha de cabeçalho
        for idx, linha in enumerate(linhas):
            if 'rowspan="2"' in linha:
                assert idx + 1 < len(linhas), "célula mesclada ficou sem a linha que ela cobre"


def test_dividir_tabela_ignora_bloco_que_nao_e_tabela():
    from conversorsei.particionador import dividir_tabela

    paragrafo = f'<p class="Texto_Justificado">{"a" * 9000}</p>'
    assert dividir_tabela(paragrafo, max_bytes=1000) == [paragrafo]


def test_dividir_em_partes_quebra_tabela_grande():
    tabela = _tabela_html([_linha(i) for i in range(60)])
    partes = dividir_em_partes([tabela], max_bytes=8000)

    assert len(partes) >= 3
    for parte in partes:
        corpo = "".join(parte)
        assert len(corpo.encode("utf-8")) <= 8000
        assert corpo.count("Descrição") == len(parte)
