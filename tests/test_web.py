import json

import pytest

from conversao_sei.core import avisos_de_blocos_grandes
from conversao_sei.particionador import BYTES_POR_KB, LIMITE_SEI_BYTES
from conversao_sei.web import converter_documento_memoria, converter_memoria_json


def test_converter_documento_memoria_md():
    md_bytes = b"""# 1. ASSUNTO

1.1. Detalhe da minuta institucional."""
    res = converter_documento_memoria(
        nome_arquivo="minuta.md",
        conteudo_bytes=md_bytes,
        max_kb=22,
    )
    assert res["sucesso"] is True
    assert res["total_partes"] == 1
    assert len(res["arquivos"]) == 1
    assert res["arquivos"][0]["nome"] == "minuta_SEI.html"
    assert "Item_Nivel1" in res["arquivos"][0]["conteudo"]
    assert "ASSUNTO" in res["arquivos"][0]["conteudo"]


def test_converter_memoria_json():
    txt_bytes = b"""1. INTRODUCAO

Texto introdutorio.

2. DESENVOLVIMENTO

Mais texto."""
    json_str = converter_memoria_json(
        nome_arquivo="despacho.txt",
        conteudo_bytes=txt_bytes,
    )
    data = json.loads(json_str)
    assert data["sucesso"] is True
    assert len(data["arquivos"]) == 1
    assert data["arquivos"][0]["nome"] == "despacho_SEI.html"


@pytest.mark.parametrize(
    "conteudo",
    ["Rua A, 1\nBrasília".encode("utf-16"), "Rua A, 1\nBrasília".encode("utf-16-le")],
)
def test_texto_utf16_mantem_acentos_e_linhas(conteudo):
    """TXT salvo pelo editor do Windows não pode falhar como XML incompatível."""
    res = converter_documento_memoria("endereco.txt", conteudo, so_corpo=True)
    assert res["sucesso"] is True
    assert "Brasília" in res["arquivos"][0]["conteudo"]


def test_texto_windows_1252_mantem_acentos():
    res = converter_documento_memoria("endereco.txt", "Brasília".encode("cp1252"), so_corpo=True)
    assert res["sucesso"] is True
    assert "Brasília" in res["arquivos"][0]["conteudo"]


@pytest.mark.parametrize(
    "nome,conteudo,orientacao",
    [
        ("legado.doc", b"texto", "salve como .docx ou .odt"),
        ("protegido.docx", b"nao e zip", "protegido por senha"),
        ("danificado.pdf", b"%PDF-1.4\nquebrado", "exporte uma nova cópia"),
    ],
)
def test_erro_comum_orienta_a_pessoa(nome, conteudo, orientacao):
    res = converter_documento_memoria(nome, conteudo)
    assert res["sucesso"] is False
    assert orientacao in res["erros"][0]
    assert "File is not a zip file" not in res["erros"][0]


def test_markdown_com_imagem_nao_cria_link_quebrado_em_silencio():
    res = converter_documento_memoria("figura.md", b"![grafico](fig.png)", so_corpo=True)
    assert res["sucesso"] is True
    assert "Imagem não incorporada" in res["arquivos"][0]["conteudo"]
    assert 'href="fig.png"' not in res["arquivos"][0]["conteudo"]
    assert any("Imagens indicadas" in aviso for aviso in res["avisos"])


def test_markdown_com_nota_avisa_que_ficou_literal():
    res = converter_documento_memoria("notas.md", b"Texto[^1]\n\n[^1]: Fonte", so_corpo=True)
    assert res["sucesso"] is True
    assert any("Notas de rodapé" in aviso for aviso in res["avisos"])


def test_markdown_de_tarefas_mostra_o_estado_sem_colchetes():
    res = converter_documento_memoria("tarefas.md", b"- [ ] Revisar\n- [x] Aprovar", so_corpo=True)
    assert res["sucesso"] is True
    html = res["arquivos"][0]["conteudo"]
    assert "Pendente: Revisar" in html
    assert "Concluído: Aprovar" in html
    assert "[ ]" not in html and "[x]" not in html


def test_markdown_subitem_mantem_recuo_e_hierarquia():
    res = converter_documento_memoria(
        "lista.md", b"1. Assunto\n  - Primeiro subitem\n    - Subitem interno\n  - Segundo subitem", so_corpo=True
    )
    assert res["sucesso"] is True
    html = res["arquivos"][0]["conteudo"]
    assert '<ul style="margin-left:2em">' in html
    assert "Primeiro subitem<ul>" in html
    assert "Subitem interno" in html and "Segundo subitem" in html


def test_imagem_grande_recebe_acao_possivel():
    bloco = '<p class="Texto_Justificado"><img src="data:image/png;base64,' + "A" * 30000 + '" /></p>'
    avisos = avisos_de_blocos_grandes([bloco], max_kb=22, so_corpo=False, forcar_unico=False)
    assert "Reduza a imagem" in avisos[0]


def test_resultado_diz_se_cada_arquivo_cabe_no_limite_do_sei_pro():
    """A interface mostra se o arquivo cabe numa colagem, e não só o tamanho.

    Com "forçar arquivo único", um documento grande passa do limite: é o caso em que o
    aviso importa.
    """
    paragrafo = "Texto do parágrafo que se repete para passar do limite do SEI Pro. " * 5
    grande = "\n\n".join(f"{i}. {paragrafo}" for i in range(1, 200)).encode("utf-8")

    unico = converter_documento_memoria("grande.txt", grande, forcar_unico=True)
    assert unico["limite_kb"] == LIMITE_SEI_BYTES // BYTES_POR_KB
    assert unico["arquivos"][0]["tamanho_bytes"] > LIMITE_SEI_BYTES
    assert unico["arquivos"][0]["cabe_no_limite"] is False

    partes = converter_documento_memoria("grande.txt", grande)
    assert len(partes["arquivos"]) > 1
    assert all(arq["cabe_no_limite"] for arq in partes["arquivos"])


def test_converter_documento_memoria_ignora_diretorios_no_nome():
    """Nome com caminho (../, subpasta/) é reduzido ao arquivo antes de virar a saída."""
    res = converter_documento_memoria(
        nome_arquivo="../../evil.md",
        conteudo_bytes=b"# 1. ASSUNTO\n\n1.1. Texto.",
    )
    assert res["sucesso"] is True
    assert res["arquivos"][0]["nome"] == "evil_SEI.html"
    assert "/" not in res["arquivos"][0]["nome"]


@pytest.mark.parametrize("nome", ["", ".", "..", "/", "../.."])
def test_converter_documento_memoria_rejeita_nome_invalido(nome):
    with pytest.raises(ValueError):
        converter_documento_memoria(nome_arquivo=nome, conteudo_bytes=b"texto")


def test_conversao_web_nao_toca_no_disco(tmp_path, monkeypatch):
    """A interface web roda sobre o sistema de arquivos emulado do WebAssembly.

    Gravar entrada e saída em arquivos temporários só para relê-los em seguida custa
    caro nesse ambiente, então a conversão inteira acontece em memória.
    """
    import tempfile

    def proibido(*args, **kwargs):
        raise AssertionError("a conversão em memória não deve criar arquivo temporário")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", proibido)
    monkeypatch.setattr(tempfile, "mkdtemp", proibido)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", proibido)

    # Um diretório vazio como diretório de trabalho: qualquer gravação relativa cairia aqui
    monkeypatch.chdir(tmp_path)

    res = converter_documento_memoria(
        nome_arquivo="minuta.md",
        conteudo_bytes=b"# 1. ASSUNTO\n\n1.1. Texto da minuta.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
    )
    assert res["sucesso"] is True
    assert "Item_Nivel1" in res["arquivos"][0]["conteudo"]
    assert "<table" in res["arquivos"][0]["conteudo"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "nome,conteudo",
    [
        ("nota.md", b"# 1. ASSUNTO\n\n1.1. Texto."),
        ("nota.txt", b"1. ASSUNTO\n\nTexto do documento."),
    ],
)
def test_web_e_cli_geram_o_mesmo_html(tmp_path, nome, conteudo):
    """A refatoração não pode fazer a web divergir da CLI: o HTML tem de ser idêntico."""
    from conversao_sei.core import converter_documento

    entrada = tmp_path / nome
    entrada.write_bytes(conteudo)
    res_disco = converter_documento(entrada, outdir=tmp_path / "saida")
    assert res_disco.sucesso, res_disco.erros

    res_memoria = converter_documento_memoria(nome_arquivo=nome, conteudo_bytes=conteudo)
    assert res_memoria["sucesso"] is True

    assert [p.name for p in res_disco.arquivos_gerados] == [a["nome"] for a in res_memoria["arquivos"]]
    for gerado, em_memoria in zip(res_disco.arquivos_gerados, res_memoria["arquivos"], strict=True):
        assert gerado.read_text(encoding="utf-8") == em_memoria["conteudo"]


def test_web_particiona_e_continua_a_numeracao_como_a_cli(tmp_path):
    """Documento grande: as partes em memória precisam seguir a mesma numeração."""
    from conversao_sei.core import converter_documento

    linhas = []
    for i in range(1, 40):
        linhas.append(f"# {i}. SECAO {i}")
        linhas.append("Texto de preenchimento. " * 40)
    conteudo = "\n\n".join(linhas).encode("utf-8")

    entrada = tmp_path / "grande.md"
    entrada.write_bytes(conteudo)
    res_disco = converter_documento(entrada, outdir=tmp_path / "saida")
    res_memoria = converter_documento_memoria(nome_arquivo="grande.md", conteudo_bytes=conteudo)

    assert len(res_disco.arquivos_gerados) > 1
    assert res_memoria["total_partes"] == len(res_disco.arquivos_gerados)
    for gerado, em_memoria in zip(res_disco.arquivos_gerados, res_memoria["arquivos"], strict=True):
        assert gerado.name == em_memoria["nome"]
        assert gerado.read_text(encoding="utf-8") == em_memoria["conteudo"]


def _origem_binaria(tmp_path, extensao):
    """Grava em disco um documento de exemplo no formato pedido."""
    from tests.test_odt_converter import _odt
    from tests.test_pdf_converter import _pdf_minimo

    if extensao == ".docx":
        from conversao_sei.md_converter import markdown_para_docx

        origem = tmp_path / "doc.docx"
        md = tmp_path / "doc.md"
        md.write_text("# 1. ASSUNTO\n\n1.1. Texto do documento.", encoding="utf-8")
        markdown_para_docx(md, origem)
        return origem
    if extensao == ".odt":
        return _odt(tmp_path)
    return _pdf_minimo(tmp_path / "doc.pdf", ["1. ASSUNTO", "", "Texto do documento."])


@pytest.mark.parametrize("extensao", [".docx", ".odt", ".pdf"])
def test_formatos_binarios_convertem_direto_dos_bytes(tmp_path, extensao):
    """Os leitores binários precisam aceitar o conteúdo que vem do navegador.

    O .pdf é o caso sensível: com um caminho em disco a extração tenta o pdftotext, que
    é um programa externo; a partir de bytes o trabalho fica com o pypdf.
    """
    origem = _origem_binaria(tmp_path, extensao)

    res = converter_documento_memoria(
        nome_arquivo=f"documento{extensao}",
        conteudo_bytes=origem.read_bytes(),
    )
    assert res["sucesso"] is True, res["erros"]
    assert "ASSUNTO" in res["arquivos"][0]["conteudo"]


@pytest.mark.parametrize("extensao", [".docx", ".odt"])
def test_web_e_cli_geram_o_mesmo_html_nos_formatos_binarios(tmp_path, extensao):
    """Paridade também nos leitores binários, que foi onde o caminho de leitura mudou.

    O .pdf fica de fora de propósito: em disco a extração pode usar o pdftotext e em
    memória usa o pypdf, então os dois lados podem divergir por projeto.
    """
    from conversao_sei.core import converter_documento

    origem = _origem_binaria(tmp_path, extensao)

    res_disco = converter_documento(origem, outdir=tmp_path / "saida")
    assert res_disco.sucesso, res_disco.erros

    res_memoria = converter_documento_memoria(
        nome_arquivo=origem.name, conteudo_bytes=origem.read_bytes()
    )
    assert res_memoria["sucesso"] is True, res_memoria["erros"]

    assert [p.name for p in res_disco.arquivos_gerados] == [a["nome"] for a in res_memoria["arquivos"]]
    for gerado, em_memoria in zip(res_disco.arquivos_gerados, res_memoria["arquivos"], strict=True):
        assert gerado.read_text(encoding="utf-8") == em_memoria["conteudo"]


def test_resultado_carrega_o_nome_do_documento_de_origem():
    """O modo em lote separa as saídas pela origem, que vem do próprio resultado."""
    res = converter_documento_memoria(
        nome_arquivo="subpasta/Nota_Tecnica_12.md",
        conteudo_bytes=b"# 1. ASSUNTO\n\n1.1. Texto.",
    )
    assert res["nome_origem"] == "Nota_Tecnica_12.md"
    assert res["arquivos"][0]["nome"] == "Nota_Tecnica_SEI_12.html"


@pytest.mark.parametrize(
    "nome,conteudo",
    [
        ("contrato.docx", b"isto nao e um docx"),
        ("planilha.odt", b"isto nao e um odt"),
    ],
)
def test_erro_cita_o_arquivo_enviado_e_nao_um_nome_generico(nome, conteudo):
    """A mensagem precisa nomear o arquivo do usuário: ele não conhece 'documento.odt'."""
    res = converter_documento_memoria(nome_arquivo=nome, conteudo_bytes=conteudo)

    assert res["sucesso"] is False
    assert res["erros"] and nome in res["erros"][0]
    assert "documento." not in res["erros"][0]


def test_md_com_fim_de_linha_do_windows_converte_igual_ao_unix():
    """Os bytes vêm do navegador como estão: um arquivo salvo no Windows chega em CRLF."""
    corpo = "# 1. ASSUNTO\n\n<red>linha um\nlinha dois</red>\n"

    unix = converter_documento_memoria("minuta.md", corpo.encode("utf-8"))
    windows = converter_documento_memoria("minuta.md", corpo.replace("\n", "\r\n").encode("utf-8"))

    assert unix["sucesso"] is True and windows["sucesso"] is True
    assert unix["arquivos"][0]["conteudo"] == windows["arquivos"][0]["conteudo"]


def test_fonte_de_tipo_invalido_falha_com_mensagem_clara():
    """O tipo vem de fora do Python (o to_py do Pyodide): o erro tem de dizer o quê."""
    from conversao_sei.entrada import abrir_binario

    with pytest.raises(TypeError, match="Fonte de documento inválida"):
        with abrir_binario(123):  # type: ignore[arg-type]
            pass


def test_rtf_nao_e_mais_aceito_e_a_mensagem_diz_por_que():
    """O .rtf saiu dos formatos aceitos: quem enviar um fica sabendo e recebe a alternativa."""
    res = converter_documento_memoria(nome_arquivo="contrato.rtf", conteudo_bytes=b"{\\rtf1 texto}")

    assert res["sucesso"] is False
    assert "contrato.rtf" in res["erros"][0]
    assert "não é mais aceito" in res["erros"][0]
    assert ".docx ou .odt" in res["erros"][0]


def test_txt_utf8_com_byte_perdido_mantem_os_acentos_e_avisa():
    """Um byte inválido não pode fazer o arquivo inteiro ser lido como Windows-1252."""
    conteudo = "Informação técnica".encode() + b" \xe9 " + "ação".encode()
    res = converter_documento_memoria("nota.txt", conteudo, so_corpo=True)
    assert res["sucesso"] is True
    html = res["arquivos"][0]["conteudo"]
    assert "Informação técnica" in html and "ação" in html
    assert "Ã" not in html
    assert any("não puderam ser lidos" in aviso for aviso in res["avisos"])


def test_markdown_expressao_em_codigo_nao_vira_aviso_de_nota():
    md = b"Texto.\n\n```\n[^0-9]: nao e nota\n```\n\nFiltro [^0-9] no texto."
    res = converter_documento_memoria("regex.md", md, so_corpo=True)
    assert res["sucesso"] is True
    assert not any("Notas de rodapé" in aviso for aviso in res["avisos"])


def test_markdown_cerca_sem_fechamento_nao_protege_imagem():
    """Cerca sem fechamento é texto na montagem, e nos avisos também."""
    res = converter_documento_memoria("figura.md", b"```\n\n![grafico](fig.png)", so_corpo=True)
    assert res["sucesso"] is True
    html = res["arquivos"][0]["conteudo"]
    assert "Imagem não incorporada" in html
    assert 'href="fig.png"' not in html


NOTA_COM_CABECALHO = (
    "# NOTA TÉCNICA Nº 12/2026/CGDI\n\n"
    "PROCESSO Nº 00000.000000/2026-00\n\n"
    "INTERESSADO: Coordenação\n\n"
    "## 1. ASSUNTO\n\n"
    "Texto do assunto.\n\n"
    "## 2. ANÁLISE\n\n"
    "Texto da análise.\n"
).encode()


def test_cabecalho_antes_do_item1_e_listado_mas_mantido_por_padrao():
    res = converter_documento_memoria("nota.md", NOTA_COM_CABECALHO, so_corpo=True)
    assert res["sucesso"] is True
    assert res["cabecalho_paragrafos"] == 3
    assert res["cabecalho_trechos"][0].startswith("NOTA TÉCNICA")
    assert "PROCESSO Nº" in res["arquivos"][0]["conteudo"]


def test_omitir_cabecalho_comeca_a_saida_no_item1():
    res = converter_documento_memoria("nota.md", NOTA_COM_CABECALHO, so_corpo=True, omitir_cabecalho=True)
    assert res["sucesso"] is True
    html = res["arquivos"][0]["conteudo"]
    assert html.lstrip().startswith('<p class="Item_Nivel1">')
    assert "NOTA TÉCNICA" not in html and "PROCESSO" not in html
    assert "Texto da análise." in html
    # A contagem continua, para a interface oferecer o desfazer
    assert res["cabecalho_paragrafos"] == 3
    assert not any("numeração" in aviso for aviso in res["avisos"])


def test_sem_item1_nada_e_omitido():
    conteudo = b"Primeiro paragrafo.\n\nSegundo paragrafo."
    res = converter_documento_memoria("carta.md", conteudo, so_corpo=True, omitir_cabecalho=True)
    assert res["sucesso"] is True
    assert res["cabecalho_paragrafos"] == 0
    assert "Primeiro paragrafo." in res["arquivos"][0]["conteudo"]


def test_cabecalho_vale_para_paragrafos_numerados():
    from conversao_sei.core import separar_cabecalho

    blocos = [
        '<p class="Texto_Centralizado">OFÍCIO</p>',
        '<p class="Paragrafo_Numerado_Nivel1">Primeiro parágrafo.</p>',
        '<p class="Paragrafo_Numerado_Nivel1">Segundo parágrafo.</p>',
    ]
    cabecalho, corpo = separar_cabecalho(blocos)
    assert cabecalho == blocos[:1]
    assert corpo == blocos[1:]
