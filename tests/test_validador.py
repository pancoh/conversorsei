from conversorsei.validador import validar_html_sei


def test_validar_html_sei_correto():
    html = """<!DOCTYPE html><html><body>
    <p class="Item_Nivel1">ASSUNTO</p>
    <p class="Item_Nivel2">Detalhamento do assunto.</p>
    <table border="1" cellpadding="1" cellspacing="1" style="width:100%;">
      <tbody>
        <tr>
          <td style="width:100%; background-color:#e6e6e6; vertical-align:middle;">
            <p class="Tabela_Texto_Centralizado"><strong>Título</strong></p>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="Texto_Justificado">Parágrafo final.</p>
    </body></html>"""

    falhas = validar_html_sei(html)
    assert falhas == []


def test_validar_html_detecta_classes_invalidas():
    html = '<p class="ClasseInventada">Texto</p>'
    falhas = validar_html_sei(html)
    assert any("um estilo de parágrafo que o SEI não reconhece" in f for f in falhas)


def test_validar_html_detecta_tags_proibidas():
    html = '<div class="Texto_Justificado"><h1>Título</h1></div>'
    falhas = validar_html_sei(html)
    assert any("editor do SEI não aceita" in f for f in falhas)


def test_validar_html_detecta_markdown_residual():
    html = '<p class="Texto_Justificado">[Clique aqui](https://gov.br) e --- </p>'
    falhas = validar_html_sei(html)
    assert any("link ficou como texto" in f for f in falhas)


def test_validar_html_detecta_url_corrompida():
    html = '<p class="Texto_Justificado">ccivil<em>03</em></p>'
    falhas = validar_html_sei(html)
    assert any("endereço de internet pode ter sido alterado" in f for f in falhas)


def test_validar_html_detecta_salto_de_nivel():
    html = """
    <p class="Item_Nivel1">ASSUNTO</p>
    <p class="Item_Nivel3">Salto direto para o nível 3</p>
    """
    falhas = validar_html_sei(html)
    assert any("salta do nível 1 para o 3" in f for f in falhas)


def test_validar_html_detecta_li_sem_classe():
    html = "<ul><li>Item sem classe institucional</li></ul>"
    falhas = validar_html_sei(html)
    assert any("item de lista pode perder" in f for f in falhas)

    html_ok = '<ul><li class="Texto_Justificado">Item com classe</li></ul>'
    assert validar_html_sei(html_ok) == []


def test_paragrafo_numerado_orfao_e_apontado():
    """Paragrafo_Numerado_Nivel2 sem o nivel 1 antes numera "0.1" no SEI."""
    html = (
        '<p class="Paragrafo_Numerado_Nivel2">Texto do parágrafo.</p>\n'
        '<p class="Paragrafo_Numerado_Nivel2">Outro parágrafo.</p>'
    )
    falhas = validar_html_sei(html)
    assert any("falta um item do nível 1" in f for f in falhas)


def test_paragrafo_numerado_em_sequencia_passa():
    html = (
        '<p class="Paragrafo_Numerado_Nivel1">Primeiro parágrafo.</p>\n'
        '<p class="Paragrafo_Numerado_Nivel2">Subparágrafo.</p>\n'
        '<p class="Paragrafo_Numerado_Nivel1">Segundo parágrafo.</p>'
    )
    assert validar_html_sei(html) == []


def test_salto_de_nivel_em_paragrafo_numerado():
    html = (
        '<p class="Paragrafo_Numerado_Nivel1">Primeiro parágrafo.</p>\n'
        '<p class="Paragrafo_Numerado_Nivel3">Salto direto para o nível 3.</p>'
    )
    falhas = validar_html_sei(html)
    assert any("salta do nível 1 para o 3" in f for f in falhas)


def test_mensagem_de_nivel_diz_qual_numeracao_conferir():
    html = (
        '<p class="Item_Nivel2">Título órfão.</p>\n'
        '<p class="Paragrafo_Numerado_Nivel2">Parágrafo órfão.</p>'
    )
    falhas = validar_html_sei(html)
    assert any(f.startswith("A numeração dos títulos e itens começa") for f in falhas)
    assert any(f.startswith("A numeração dos parágrafos numerados começa") for f in falhas)


def test_documento_grande_nao_recebe_aviso_de_tamanho():
    """O limite de tamanho era o do plugin SEI Pro: a colagem direta leva o documento inteiro."""
    texto = '<p class="Texto_Justificado">' + "a" * 30000 + "</p>"
    assert validar_html_sei(texto) == []


def test_validar_arquivo_so_avisa_a_cerca_quando_a_origem_e_markdown(tmp_path):
    from conversorsei.validador import validar_arquivo_sei

    arquivo = tmp_path / "saida_SEI.html"
    arquivo.write_text('<body><p class="Texto_Justificado">```</p></body>', encoding="utf-8")
    assert validar_arquivo_sei(arquivo) == []
    assert any("três crases" in aviso for aviso in validar_arquivo_sei(arquivo, origem_markdown=True))
