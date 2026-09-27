from conversorsei.md_converter import converter_md_para_html
from conversorsei.pdf_converter import (
    estruturar_texto_para_markdown,
    limpar_boilerplate_sei,
    remontar_numeracao,
)


def test_limpar_boilerplate_sei():
    texto_bruto = """MINISTÉRIO DAS CIDADES
DESPACHO
Processo nº 80000.007729/2026-93

1. ASSUNTO
1.1. Texto do despacho.

(assinatura eletrônica)
[assinado eletronicamente]
Documento assinado eletronicamente por Glauto Wolfgang da Silva, em 06/07/2026, com fundamento no art. 4º, § 3º, do Decreto nº 10.543, de 13 de novembro de 2020.
A autenticidade do documento pode ser conferida no site sei.gov.br informando o código verificador 6809741 e o código CRC 8A5C6CC8.
"""
    limpo = limpar_boilerplate_sei(texto_bruto)
    assert "Documento assinado eletronicamente" not in limpo
    assert "código CRC" not in limpo
    assert "(assinatura eletrônica)" not in limpo
    assert "[assinado eletronicamente]" not in limpo
    assert "1. ASSUNTO" in limpo


def test_estruturar_texto_para_markdown():
    texto = """1. ASSUNTO

1.1. Texto explicativo do processo administrativo.

CONCLUSÃO

Manifestação favorável ao pleito formulado."""

    md = estruturar_texto_para_markdown(texto)
    assert "# 1. ASSUNTO" in md
    assert "1.1. Texto explicativo" in md
    assert "## CONCLUSÃO" in md


def _pdf_minimo(caminho, linhas):
    """Gera um PDF simples e válido, sem depender de biblioteca de escrita."""
    conteudo = "BT /F1 12 Tf 50 750 Td 14 TL\n"
    for linha in linhas:
        texto = linha.replace("(", r"\(").replace(")", r"\)")
        conteudo += f"({texto}) Tj T*\n"
    conteudo += "ET"

    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
    ]

    saida = "%PDF-1.4\n"
    posicoes = []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += f"{i} 0 obj\n{obj}\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n"
    for pos in posicoes:
        saida += f"{pos:010d} 00000 n \n"
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n"
    )
    caminho.write_bytes(saida.encode("latin-1"))
    return caminho


def test_pdf_conversao_ponta_a_ponta(tmp_path):
    """PDF -> texto -> limpeza -> markdown -> blocos SEI, sem sobras de boilerplate."""
    from conversorsei.core import converter_documento

    pdf = _pdf_minimo(
        tmp_path / "despacho.pdf",
        [
            "1. ASSUNTO",
            "",
            "Trata-se de analise tecnica sobre o objeto do processo.",
            "",
            "2. CONCLUSAO",
            "",
            "Encaminhe-se para providencias.",
            "",
            "Documento assinado eletronicamente por Fulano de Tal, Diretor,",
            "em 10/10/2026, conforme codigo CRC A1B2C3D4.",
        ],
    )

    resultado = converter_documento(pdf, outdir=tmp_path / "saida")
    assert resultado.sucesso, resultado.erros
    assert len(resultado.arquivos_gerados) == 1

    html = resultado.arquivos_gerados[0].read_text(encoding="utf-8")
    assert "ASSUNTO" in html
    assert "analise tecnica" in html
    # O carimbo de assinatura eletrônica não sobrevive à limpeza
    assert "assinado eletronicamente" not in html.lower()
    assert "CRC" not in html


def test_pdf_extracao_funciona_sem_pdftotext(tmp_path, monkeypatch):
    """O fallback em pypdf precisa funcionar: o runner do CI não tem o binário pdftotext."""
    import shutil as shutil_mod

    from conversorsei import pdf_converter

    monkeypatch.setattr(pdf_converter.shutil, "which", lambda _: None)
    assert shutil_mod.which  # o módulo real segue intacto

    pdf = _pdf_minimo(tmp_path / "so_pypdf.pdf", ["1. ASSUNTO", "", "Texto extraido pelo pypdf."])
    texto = pdf_converter.extrair_texto_pdf(pdf)
    assert "ASSUNTO" in texto
    assert "pypdf" in texto


def test_remontar_numeracao_quebrada_pelo_extrator():
    """O pypdf devolve "1", ".", "1", "." em linhas separadas do texto do item."""
    linhas = ["1", ".", "ASSUNTO", "1", ".", "1", ".", "Trata-se de análise do projeto."]
    assert remontar_numeracao(linhas) == ["1. ASSUNTO", "1.1. Trata-se de análise do projeto."]


def test_remontar_numeracao_com_texto_na_linha_seguinte():
    """O pdftotext deixa "1.1." sozinho e o texto do item na linha de baixo."""
    linhas = ["1.1.", "", "Trata-se de análise do projeto."]
    assert remontar_numeracao(linhas) == ["1.1. Trata-se de análise do projeto."]


def test_estruturar_texto_sem_linha_em_branco():
    """Extrator de PDF quebra a frase em linhas e não marca o fim do parágrafo.

    Sem reagrupar pela numeração, o documento inteiro sai como um único parágrafo.
    """
    texto = """Ministério das Cidades
Secretaria Nacional de Mobilidade Urbana
1. ASSUNTO
1.1. Trata-se de solicitação de análise do Projeto de Lei
Substitutivo nº 4768, de 2020, de autoria do Deputado Federal
Cláudio Cajado.
1.2. A iniciativa altera a Lei nº 12.587, de 2012.
2. CONCLUSÃO
2.1. Manifestação contrária."""

    md = estruturar_texto_para_markdown(texto)
    linhas = [ln for ln in md.split("\n") if ln.strip()]
    assert linhas == [
        '<p class="Texto_Centralizado">Ministério das Cidades</p>',
        '<p class="Texto_Centralizado">Secretaria Nacional de Mobilidade Urbana</p>',
        "# 1. ASSUNTO",
        "1.1. Trata-se de solicitação de análise do Projeto de Lei Substitutivo nº 4768, "
        "de 2020, de autoria do Deputado Federal Cláudio Cajado.",
        "1.2. A iniciativa altera a Lei nº 12.587, de 2012.",
        "# 2. CONCLUSÃO",
        "2.1. Manifestação contrária.",
    ]


def test_limpar_rodape_de_pagina_do_sei():
    """O rodapé de cada página cai no meio da frase que a quebra de página cortou."""
    texto = """1.1. A Política Nacional de Mobilidade Urbana constitui instrumento da política de

                  Nota Técnica 110 (6900388)         SEI 80000.006816/2026-23 / pg. 1
desenvolvimento urbano.
Referência: Processo nº 80000.006816/2026-23          SEI nº 6900388
"""
    limpo = limpar_boilerplate_sei(texto)
    assert "pg. 1" not in limpo
    assert "Nota Técnica 110" not in limpo
    assert "Referência:" not in limpo
    # A frase cortada pela quebra de página emenda direto, sem linha em branco no meio
    assert "instrumento da política de\ndesenvolvimento urbano." in limpo


def test_quebra_de_pagina_nao_parte_o_paragrafo():
    """O parágrafo cortado pela quebra de página precisa sair inteiro, num bloco só."""
    texto = """1.1. A Política Nacional de Mobilidade Urbana constitui instrumento da política de

                  Nota Técnica 110 (6900388)         SEI 80000.006816/2026-23 / pg. 1
desenvolvimento urbano destinado a orientar o planejamento.
1.2. Item seguinte."""

    md = estruturar_texto_para_markdown(limpar_boilerplate_sei(texto))
    linhas = [ln for ln in md.split("\n") if ln.strip()]
    assert linhas == [
        "1.1. A Política Nacional de Mobilidade Urbana constitui instrumento da política de "
        "desenvolvimento urbano destinado a orientar o planejamento.",
        "1.2. Item seguinte.",
    ]


def test_cabecalho_do_pdf_sai_centralizado():
    """Órgão, unidade e identificação do documento são centralizados no padrão SEI."""
    texto = """Ministério das Cidades
Secretaria Nacional de Mobilidade Urbana
PROCESSO Nº 80000.006816/2026-23
1. ASSUNTO
1.1. Trata-se de análise do projeto.
2. CONCLUSÃO
2.1. BIANCA DA VEIGA ARAUJO assina o documento."""

    md = estruturar_texto_para_markdown(texto)
    assert md.count('<p class="Texto_Centralizado">') == 3
    assert '<p class="Texto_Centralizado">PROCESSO Nº 80000.006816/2026-23</p>' in md
    # O corpo não é afetado pela centralização do cabeçalho
    assert "# 1. ASSUNTO" in md
    assert "1.1. Trata-se de análise do projeto." in md


def test_pdf_sem_camada_de_texto_avisa_sobre_ocr(tmp_path):
    """PDF digitalizado nao tem o que extrair: o erro precisa dizer isso."""
    import pytest

    from conversorsei import pdf_converter

    pdf = _pdf_minimo(tmp_path / "digitalizado.pdf", [])
    with pytest.raises(RuntimeError, match="camada de texto"):
        pdf_converter.extrair_texto_pdf(pdf)


def test_marcacao_markdown_do_pdf_nao_vira_formatacao(tmp_path):
    """O texto do PDF passa pelo conversor de Markdown e nao pode ser lido como marcacao."""
    texto = """1. ASSUNTO
1.1. O item foi avaliado com *cautela*, num total de 2 * 3 unidades.
1.2. O art. 5º [conforme a Lei] trata do tema."""

    md_file = tmp_path / "extraido.md"
    md_file.write_text(estruturar_texto_para_markdown(texto), encoding="utf-8")

    html = converter_md_para_html(md_file)
    assert "<em>" not in html
    assert "com *cautela*, num total de 2 * 3 unidades." in html
    assert "O art. 5º [conforme a Lei] trata do tema." in html
    assert "\\" not in html


def test_pdftotext_decodificado_como_utf8(tmp_path, monkeypatch):
    """A saída do pdftotext é UTF-8 e precisa ser decodificada como tal.

    Sem `encoding` explícito, o subprocess usa a codificação preferida do sistema
    (cp1252 no Windows) e os acentos do documento chegam corrompidos ao HTML.
    """
    import subprocess

    from conversorsei import pdf_converter

    chamada = {}

    def falso_run(cmd, **kwargs):
        chamada.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="Análise da concessão.\n", stderr="")

    monkeypatch.setattr(pdf_converter.shutil, "which", lambda _: "/usr/bin/pdftotext")
    monkeypatch.setattr(pdf_converter.subprocess, "run", falso_run)

    texto = pdf_converter.extrair_texto_pdf(tmp_path / "qualquer.pdf")
    assert texto == "Análise da concessão.\n"
    assert chamada["encoding"] == "utf-8"
    assert chamada["errors"] == "replace"


def test_pdf_para_blocos_nao_grava_arquivo_temporario(tmp_path, monkeypatch):
    """O .md e o .docx intermediários são etapa interna e ficam em memória.

    Gravá-los custava duas idas ao disco por PDF, o que pesa na conversão em lote e
    no ambiente WASM da interface web.
    """
    import tempfile

    from conversorsei import pdf_converter

    def proibido(*args, **kwargs):
        raise AssertionError("a conversão de PDF não deve criar diretório temporário")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", proibido)
    monkeypatch.setattr(tempfile, "mkdtemp", proibido)

    pdf = _pdf_minimo(
        tmp_path / "sem_temp.pdf",
        ["1. ASSUNTO", "", "Trata-se de analise tecnica sobre o objeto do processo."],
    )
    html = "\n".join(pdf_converter.converter_pdf_para_blocos(pdf))
    assert "ASSUNTO" in html
    assert "analise tecnica" in html


def test_limpar_cabecalho_dos_tipos_documentais_frequentes():
    """O cabeçalho residual ("Memorando 6900388") sobra na extração e precisa sair.

    O número de seis a oito dígitos é o do documento no SEI: sem ele a linha é texto
    comum ("Portaria" como título de seção) e deve ser preservada.
    """
    tipos = [
        "Despacho",
        "Nota Técnica",
        "Ofício",
        "Parecer",
        "Memorando",
        "Portaria",
        "Informação",
        "Relatório",
        "Edital",
        "Ata",
        "Termo de Referência",
        "Decisão",
        "Instrução Normativa",
        "Comunicação Interna",
        "Circular",
        "Resolução",
        "Certidão",
        "Declaração",
        "Manifestação",
    ]
    for tipo in tipos:
        limpo = limpar_boilerplate_sei(f"1. ASSUNTO\n{tipo} 6900388\nTexto do documento.")
        assert tipo not in limpo, f"cabeçalho de {tipo!r} sobreviveu"
        assert "Texto do documento." in limpo

    # Sem o número do SEI a linha é conteúdo, não cabeçalho
    preservado = limpar_boilerplate_sei("1. ASSUNTO\nPortaria de nomeação\nTexto.")
    assert "Portaria de nomeação" in preservado
