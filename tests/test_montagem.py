from pathlib import Path

from conversorsei.montagem import (
    apagar_partes_antigas,
    css_institucional,
    derivar_caminho_saida,
    montar_html,
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
    assert "counter-reset:item-n1 0" in html
    assert corpo in html


def test_contadores_iniciais_ficam_num_irmao_dos_paragrafos_e_nao_no_body():
    """Com o counter-reset no body, o Chrome numerava 2.3 logo depois de "2.".

    O counter-reset de cada Item_Nivel1 deixava de valer para os subitens seguintes, e a
    prévia e o arquivo aberto no Chrome emendavam a numeração das seções (o Safari
    numerava certo). No body::before, irmão dos parágrafos, os dois navegadores acertam,
    e a regra fica no <style>, que não vai para o SEI na cópia.
    """
    html = montar_html('<p class="Item_Nivel1">Teste</p>')
    regra_body = html.split("body {", 1)[1].split("}", 1)[0]
    assert "counter-reset" not in regra_body
    regra_antes = html.split("body::before {", 1)[1].split("}", 1)[0]
    assert "counter-reset:item-n1 0 " in regra_antes


def test_apagar_partes_antigas_deixa_o_arquivo_unico(tmp_path):
    saida = tmp_path / "documento_SEI.html"
    partes = [tmp_path / f"documento_SEI_parte{i:02d}.html" for i in range(1, 4)]
    outro = tmp_path / "outro_SEI_parte01.html"
    saida.write_text("unico", encoding="utf-8")
    for p in [*partes, outro]:
        p.write_text("parte", encoding="utf-8")

    removidos = apagar_partes_antigas(saida)

    assert sorted(removidos) == partes
    assert saida.is_file()
    # A parte de outro documento não é desta saída
    assert outro.is_file()


def test_documento_longo_sai_em_um_arquivo_e_apaga_as_partes_antigas(tmp_path):
    """O documento sai inteiro, por maior que seja, e as partes de uma versão anterior saem.

    A divisão em partes existia para o limite de colagem do plugin SEI Pro. A cópia e a
    colagem direto no editor do SEI levam o documento longo inteiro.
    """
    from conversorsei.core import converter_documento

    linhas = []
    for i in range(1, 80):
        linhas.append(f"# {i}. SECAO {i}")
        linhas.append("Texto de preenchimento. " * 40)
    entrada = tmp_path / "grande.md"
    entrada.write_text("\n\n".join(linhas), encoding="utf-8")
    parte_velha = tmp_path / "grande_SEI_parte01.html"
    parte_velha.write_text("parte de uma conversão antiga", encoding="utf-8")

    res = converter_documento(entrada, outdir=tmp_path)

    assert res.sucesso
    assert res.arquivos_gerados == [tmp_path / "grande_SEI.html"]
    conteudo = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert len(conteudo.encode("utf-8")) > 80_000
    assert conteudo.count('class="Item_Nivel1"') == 79
    assert not parte_velha.exists()
    assert not any("bytes" in aviso for aviso in res.avisos)


def test_derivar_caminho_saida():
    assert derivar_caminho_saida("doc.docx") == Path("doc_SEI.html")
    assert derivar_caminho_saida("Nota_Tecnica_NT_01.docx") == Path("Nota_Tecnica_SEI_NT_01.html")
    assert derivar_caminho_saida("Nota_Tecnica_Revisada_NT_02.docx") == Path("Nota_Tecnica_SEI_NT_02.html")
    assert derivar_caminho_saida("doc.docx", so_corpo=True) == Path("doc_SEI_corpo.html")
