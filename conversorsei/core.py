"""
core.py — Orquestrador principal de conversão para documentos DOCX, PDF, ODT, HTML, MD e TXT.
"""
from __future__ import annotations

import html as htmlmod
import re
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile

from conversorsei.docx_converter import converter_docx_para_blocos
from conversorsei.entrada import FonteDocumento, StreamNomeado
from conversorsei.formatacao import CitacaoPorRecuo, trecho_inicial
from conversorsei.html_converter import EXTENSOES_HTML, converter_html_para_blocos
from conversorsei.md_converter import converter_md_para_blocos
from conversorsei.montagem import TITULO_DA_SAIDA, apagar_partes_antigas, derivar_caminho_saida, montar_html
from conversorsei.odt_converter import converter_odt_para_blocos
from conversorsei.pdf_converter import converter_pdf_para_blocos, converter_texto_de_pdf_para_blocos
from conversorsei.validador import validar_html_sei

EXTENSOES_SUPORTADAS = {".docx", ".pdf", ".md", ".txt", ".odt", *EXTENSOES_HTML}
# Formatos de editor que não são aceitos, com a orientação para quem ainda os usa. O .rtf
# saiu em 2026-09: não havia uso conhecido, e o leitor próprio de RTF era o trecho mais
# caro de manter. O .doc nunca foi aceito, mas ainda aparece nas pastas de trabalho.
FORMATOS_RETIRADOS = {
    ".rtf": "O formato .rtf não é mais aceito: salve o documento como .docx ou .odt.",
    ".doc": "O formato .doc não é aceito. Abra o arquivo no Word ou LibreOffice e salve como .docx ou .odt.",
}
# Extensões que a varredura de pastas e o modo watch enxergam. As não aceitas entram de
# propósito: viram um resultado com erro e a orientação acima, em vez de serem puladas
# em silêncio (um .rtf ou .doc deixado na pasta de entrada simplesmente sumiria da conversão).
EXTENSOES_RECONHECIDAS = frozenset(EXTENSOES_SUPORTADAS | FORMATOS_RETIRADOS.keys())
# O OCR erra letras e números sem aviso: o resultado precisa de conferência. Para muitos
# erros, o caminho é o original ou outro programa de OCR (o OCRmyPDF ficou de fora: usa o
# mesmo Tesseract e deu o mesmo resultado). São dois avisos, um por assunto: num só, o
# que conferir ficava perdido no meio das alternativas. A página mostra `**...**` em
# negrito e `[texto](endereço)` como link; no relato por e-mail, o texto vai como está
AVISOS_OCR = (
    "**O texto foi reconhecido por OCR e pode ter erros.** Confira nomes, números, datas e valores "
    "com o original antes de salvar no SEI.",
    "**Muitos erros?** Peça o documento original em Word (.docx) ou use outro programa de OCR: "
    "[PDF24](https://tools.pdf24.org/pt/ocr-pdf) (online; o documento vai para o servidor do serviço), "
    "Adobe Acrobat ou ABBYY FineReader (instalados no computador).",
)


@dataclass
class ArquivoSEI:
    """Um arquivo de saída que ainda não foi para o disco."""

    nome: str
    conteudo: str


@dataclass
class ResultadoMemoria:
    """Resultado de uma conversão feita inteiramente em memória."""

    nome_origem: str
    arquivos: list[ArquivoSEI] = field(default_factory=list)
    sucesso: bool = True
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    # Parágrafos com forma de citação, convertidos ou não: recuados e em fonte menor,
    # ou numa citação entre aspas
    citacoes_por_recuo: int = 0
    citacoes_entre_aspas: int = 0
    # Início de cada um desses parágrafos, na ordem do documento
    citacoes_trechos: list[str] = field(default_factory=list)
    # Início de cada parágrafo antes do item 1 (o cabeçalho), omitido ou não
    cabecalho_trechos: list[str] = field(default_factory=list)


@dataclass
class ResultadoConversao:
    arquivo_origem: Path
    arquivos_gerados: list[Path] = field(default_factory=list)
    sucesso: bool = True
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    # Parágrafos com forma de citação, convertidos ou não: recuados e em fonte menor,
    # ou numa citação entre aspas
    citacoes_por_recuo: int = 0
    citacoes_entre_aspas: int = 0
    # Início de cada um desses parágrafos, na ordem do documento
    citacoes_trechos: list[str] = field(default_factory=list)
    # Início de cada parágrafo antes do item 1 (o cabeçalho), omitido ou não
    cabecalho_trechos: list[str] = field(default_factory=list)


def extrair_blocos_de_fonte(
    fonte: FonteDocumento,
    sufixo: str,
    max_nivel: int = 4,
    citacao: CitacaoPorRecuo | None = None,
    avisos: list[str] | None = None,
    colado: bool = False,
) -> list[str]:
    """Extrai os blocos SEI de um documento, pelo formato indicado no sufixo.

    A fonte pode ser um caminho ou o conteúdo em memória, o que permite à interface web
    converter os bytes que vêm do navegador sem gravar arquivo temporário. Em `citacao`,
    a regra do recuo só tem efeito em .docx e .odt (Markdown, texto, HTML e PDF não têm
    recuo nem fonte); a das aspas vale em todos.
    """
    sufixo = sufixo.lower()

    if sufixo == ".docx":
        return converter_docx_para_blocos(fonte, max_nivel=max_nivel, citacao=citacao, avisos=avisos)
    elif sufixo in {".md", ".txt"}:
        # .txt não é Markdown: ">", "```" e "~~" ali são texto
        return converter_md_para_blocos(
            fonte, max_nivel=max_nivel, estendido=sufixo == ".md", avisos=avisos, citacao=citacao
        )
    elif sufixo == ".pdf":
        return converter_pdf_para_blocos(fonte, max_nivel=max_nivel, citacao=citacao)
    elif sufixo == ".odt":
        return converter_odt_para_blocos(fonte, max_nivel=max_nivel, citacao=citacao, avisos=avisos)
    elif sufixo in EXTENSOES_HTML:
        return converter_html_para_blocos(fonte, max_nivel=max_nivel, avisos=avisos, colado=colado, citacao=citacao)
    elif sufixo in FORMATOS_RETIRADOS:
        raise ValueError(FORMATOS_RETIRADOS[sufixo])
    else:
        raise ValueError(
            f"Formato não suportado: '{sufixo}'. Extensões aceitas: {', '.join(sorted(EXTENSOES_SUPORTADAS))}"
        )


def mensagem_erro_de_extracao(nome: str, erro: Exception) -> str:
    """Troca mensagens de biblioteca por uma orientação que permita tentar de novo."""
    sufixo = Path(nome).suffix.lower()
    detalhe = str(erro)
    if sufixo == ".docx" and (isinstance(erro, BadZipFile) or "File is not a zip file" in detalhe):
        return (
            f"Não foi possível abrir {nome}. O arquivo pode estar danificado ou protegido por senha. "
            "Abra no Word ou LibreOffice, retire a proteção se houver e salve uma nova cópia em .docx."
        )
    if sufixo == ".pdf" and "Falha ao extrair texto do PDF" in detalhe:
        return (
            f"Não foi possível ler {nome}. O PDF pode estar danificado ou protegido. "
            "Abra o arquivo e exporte uma nova cópia em PDF antes de tentar novamente."
        )
    return f"Não foi possível converter {nome}: {detalhe}"


# O corpo do documento começa no item 1 da numeração do SEI ("1. ASSUNTO"), nas duas
# famílias de contadores
RE_INICIO_DO_CORPO = re.compile(r'<p class="(?:Item_Nivel1|Paragrafo_Numerado_Nivel1)"')


def separar_cabecalho(blocos: list[str]) -> tuple[list[str], list[str]]:
    """Divide os blocos em cabeçalho (tudo antes do primeiro item 1) e corpo.

    No SEI, título, número e dados do processo vêm do modelo do documento, e quem cola o
    texto convertido costuma querer só o corpo. Sem item 1, não há como saber onde o
    corpo começa: tudo é corpo, e nada é omitido.
    """
    for indice, bloco in enumerate(blocos):
        if RE_INICIO_DO_CORPO.match(bloco.lstrip()):
            return blocos[:indice], blocos[indice:]
    return [], blocos


def trechos_dos_blocos(blocos: list[str]) -> list[str]:
    """Início do texto de cada bloco, para mostrar o que o cabeçalho contém.

    Bloco sem texto (a linha em branco de &nbsp;) fica de fora: não há o que reconhecer.
    """
    trechos = []
    for bloco in blocos:
        texto = htmlmod.unescape(re.sub(r"<[^>]+>", " ", bloco)).replace("\xa0", " ")
        if texto.strip():
            trechos.append(trecho_inicial(texto))
    return trechos


def aplicar_cabecalho(blocos: list[str], omitir: bool) -> tuple[list[str], list[str]]:
    """Devolve os blocos a converter e os trechos do cabeçalho encontrado.

    O cabeçalho é sempre medido, para quem converte decidir se o omite; só sai dos
    blocos quando `omitir` é verdadeiro. Compartilhada pelas duas conversões.
    """
    cabecalho, corpo = separar_cabecalho(blocos)
    return (corpo if omitir else blocos), trechos_dos_blocos(cabecalho)


def extrair_blocos_documento(
    caminho: str | Path,
    max_nivel: int = 4,
    citacao: CitacaoPorRecuo | None = None,
    avisos: list[str] | None = None,
) -> list[str]:
    """Identifica a extensão do arquivo e extrai a lista de blocos SEI."""
    p = Path(caminho)
    return extrair_blocos_de_fonte(p, p.suffix, max_nivel=max_nivel, citacao=citacao, avisos=avisos)


def montar_saida(blocos: list[str], nome_base: str, sufixo: str = ".html", so_corpo: bool = False) -> tuple[str, str]:
    """Junta os blocos num arquivo só e devolve o par (nome do arquivo, conteúdo).

    É a parte da conversão que não toca no disco, compartilhada por quem grava arquivos
    (a CLI) e por quem devolve texto (a interface web). O documento sai inteiro: a cópia
    e a colagem no editor do SEI levam a formatação de um documento longo, e a divisão em
    partes, feita para o limite do plugin SEI Pro, só obrigava a colar várias vezes.
    """
    corpo = "\n".join(blocos)
    conteudo = corpo + "\n" if so_corpo else montar_html(corpo)
    return f"{nome_base}{sufixo}", conteudo


def validar_saida(conteudo: str, origem_markdown: bool = True) -> list[str]:
    """Valida o HTML gerado e devolve os avisos.

    Compartilhada pelas duas conversões, para que a da web e a do disco não passem a
    avisar coisas diferentes sobre o mesmo HTML. `origem_markdown` diz se a entrada era
    .md: só aí ">", "```" e "~~" que sobraram no HTML indicam marcação não convertida.
    Os avisos não levam o nome do arquivo gerado: há um por documento, e quem mostra o
    aviso já diz de qual documento ele é.
    """
    return validar_html_sei(conteudo, origem_markdown=origem_markdown)


def converter_documento(
    caminho_entrada: str | Path,
    caminho_saida: str | Path | None = None,
    outdir: str | Path | None = None,
    so_corpo: bool = False,
    max_nivel: int = 4,
    validar: bool = True,
    citacao_por_recuo: bool = False,
    omitir_cabecalho: bool = False,
    destinos_reservados: dict[Path, Path] | None = None,
) -> ResultadoConversao:
    """Converte um documento (DOCX, PDF, ODT, HTML, MD, TXT) num HTML formatado para o SEI.

    Com `citacao_por_recuo`, o parágrafo recuado e em fonte menor que a do texto sai como
    Citação. Desligado, ele segue texto comum e só é contado em `citacoes_por_recuo`.
    Com `omitir_cabecalho`, o que vem antes do item 1 não entra na saída; desligado, só é
    listado em `cabecalho_trechos`.
    """
    p_in = Path(caminho_entrada)
    resultado = ResultadoConversao(arquivo_origem=p_in)

    if not p_in.is_file():
        resultado.sucesso = False
        resultado.erros.append(f"Arquivo não encontrado: {p_in}")
        return resultado

    citacao = CitacaoPorRecuo(aplicar=citacao_por_recuo)
    avisos_extracao: list[str] = []
    try:
        blocos = extrair_blocos_documento(p_in, max_nivel=max_nivel, citacao=citacao, avisos=avisos_extracao)
    except Exception as e:
        resultado.sucesso = False
        resultado.erros.append(mensagem_erro_de_extracao(p_in.name, e))
        return resultado
    resultado.citacoes_por_recuo = citacao.encontradas
    resultado.citacoes_entre_aspas = citacao.entre_aspas
    resultado.citacoes_trechos = citacao.trechos

    if not blocos:
        resultado.sucesso = False
        resultado.erros.append(f"Nenhum conteúdo extraído de {p_in.name}.")
        return resultado
    blocos, resultado.cabecalho_trechos = aplicar_cabecalho(blocos, omitir_cabecalho)
    resultado.avisos = avisos_extracao

    if caminho_saida is not None:
        saida_base = Path(caminho_saida)
    else:
        saida_base = derivar_caminho_saida(p_in, so_corpo=so_corpo, outdir=outdir)

    destino = saida_base.resolve()
    origem = p_in.resolve()
    outra_origem = (destinos_reservados or {}).get(destino)
    if outra_origem is None and destino.exists():
        outra_origem = next(
            (fonte for reservado, fonte in (destinos_reservados or {}).items() if mesmo_arquivo(destino, reservado)),
            None,
        )
    if mesmo_arquivo(destino, origem):
        resultado.sucesso = False
        resultado.erros.append(f"A saída {saida_base} é o próprio arquivo de entrada. Escolha outro nome.")
        return resultado
    if outra_origem is not None and not mesmo_arquivo(outra_origem, origem):
        # O --saida não serve ao lote nem ao watch: a orientação é a que vale nos dois
        resultado.sucesso = False
        resultado.erros.append(
            f"A saída {saida_base} coincide com a de {outra_origem.name}. "
            "Renomeie um dos dois documentos ou converta-os para pastas diferentes."
        )
        return resultado
    saida_base.parent.mkdir(parents=True, exist_ok=True)

    nome, conteudo = montar_saida(blocos, nome_base=saida_base.stem, sufixo=saida_base.suffix, so_corpo=so_corpo)
    apagar_partes_antigas(saida_base)
    caminho = saida_base.parent / nome
    caminho.write_text(conteudo, encoding="utf-8")
    if destinos_reservados is not None:
        destinos_reservados[destino] = origem
    resultado.arquivos_gerados = [caminho]

    if validar:
        # Valida o que acabou de ser montado, em vez de reler do disco o que já está aqui
        resultado.avisos.extend(validar_saida(conteudo, origem_markdown=p_in.suffix.lower() == ".md"))

    return resultado


def mesmo_arquivo(primeiro: Path, segundo: Path) -> bool:
    """O sistema de arquivos decide se nomes com caixas diferentes são o mesmo arquivo.

    As saídas reservadas já existem no disco. samefile também cobre links físicos,
    sem impedir nomes distintos em sistemas que diferenciam maiúsculas.
    """
    if primeiro == segundo:
        return True
    try:
        return primeiro.samefile(segundo)
    except OSError:
        return False


def converter_bytes(
    nome_arquivo: str,
    conteudo: bytes,
    so_corpo: bool = False,
    max_nivel: int = 4,
    validar: bool = True,
    citacao_por_recuo: bool = False,
    omitir_cabecalho: bool = False,
    texto_reconhecido: str | None = None,
    colado: bool = False,
) -> ResultadoMemoria:
    """Converte o conteúdo de um documento sem tocar no disco.

    É o caminho usado pela interface web: o navegador entrega os bytes do arquivo, e a
    conversão inteira acontece em memória. Gravar entrada e saída em arquivos
    temporários só para relê-los custa caro no sistema de arquivos emulado do
    WebAssembly, onde a página roda.

    `texto_reconhecido` é o texto que o OCR do navegador leu de um PDF digitalizado.
    Com ele, o PDF não é lido de novo (não teria o que extrair): o texto segue a
    limpeza e a estruturação do PDF com texto, e o resultado leva o aviso do OCR.

    `colado` indica conteúdo colado na página, e não um arquivo: a área de transferência
    do Word e do Google Docs traz a formatação que o leitor de HTML entende, e o aviso
    para converter o arquivo original não cabe.
    """
    origem = Path(nome_arquivo)
    resultado = ResultadoMemoria(nome_origem=origem.name)
    citacao = CitacaoPorRecuo(aplicar=citacao_por_recuo)
    avisos_extracao: list[str] = []

    try:
        # O stream leva o nome junto para que os leitores citem o arquivo que o usuário
        # enviou, e não um nome genérico, nas mensagens de erro. Fecha assim que os
        # blocos saem, para devolver a memória do navegador sem esperar o coletor
        if texto_reconhecido is not None:
            if not texto_reconhecido.strip():
                raise RuntimeError(
                    "o OCR não reconheceu texto nas páginas. Confira se a digitalização está legível."
                )
            blocos = converter_texto_de_pdf_para_blocos(texto_reconhecido, max_nivel=max_nivel, citacao=citacao)
            avisos_extracao.extend(AVISOS_OCR)
        else:
            with closing(StreamNomeado(conteudo, origem.name)) as fonte:
                blocos = extrair_blocos_de_fonte(
                    fonte, origem.suffix, max_nivel=max_nivel, citacao=citacao, avisos=avisos_extracao, colado=colado
                )
    except Exception as e:
        resultado.sucesso = False
        resultado.erros.append(mensagem_erro_de_extracao(origem.name, e))
        return resultado
    resultado.citacoes_por_recuo = citacao.encontradas
    resultado.citacoes_entre_aspas = citacao.entre_aspas
    resultado.citacoes_trechos = citacao.trechos

    if not blocos:
        resultado.sucesso = False
        resultado.erros.append(f"Nenhum conteúdo extraído de {origem.name}.")
        return resultado
    blocos, resultado.cabecalho_trechos = aplicar_cabecalho(blocos, omitir_cabecalho)
    resultado.avisos = avisos_extracao

    # A convenção de nomes é a mesma da conversão em disco (Nota_Tecnica_ vira
    # Nota_Tecnica_SEI_), para que os arquivos baixados pela web não destoem da CLI
    saida = derivar_caminho_saida(origem, so_corpo=so_corpo)

    nome, conteudo_saida = montar_saida(blocos, nome_base=saida.stem, sufixo=saida.suffix, so_corpo=so_corpo)
    resultado.arquivos = [ArquivoSEI(nome=nome, conteudo=conteudo_saida)]

    if validar:
        resultado.avisos.extend(validar_saida(conteudo_saida, origem_markdown=origem.suffix.lower() == ".md"))

    return resultado


def entra_na_varredura(arquivo: Path) -> bool:
    """Diz se um arquivo achado numa pasta deve ser convertido.

    Compartilhada pela conversão de pastas e pelo modo watch, para os dois pularem os mesmos
    arquivos. A trava do Word (~$) e os ocultos têm extensão válida, mas não são documentos:
    convertê-los só produziria falha.
    """
    if arquivo.suffix.lower() not in EXTENSOES_RECONHECIDAS or arquivo.name.startswith(("~$", ".")):
        return False
    return not eh_saida_do_conversor(arquivo)


# Nomes que derivar_caminho_saida dá à saída: "nota_SEI.html", "nota_SEI_corpo.html" e
# "Nota_Tecnica_SEI_12.html". O "_parte02" é das versões que dividiam o documento: as
# partes velhas que ficaram numa pasta também não podem ser convertidas de novo
RE_NOME_DA_SAIDA = re.compile(r"(?:_SEI|^Nota_Tecnica_SEI_.*?)(?:_corpo)?(?:_parte\d+)?\.html?$", re.IGNORECASE)


def eh_saida_do_conversor(arquivo: Path) -> bool:
    """Diz se o HTML foi gerado por este conversor, pelo nome ou pelo título.

    Sem -o, a saída vai para a pasta da entrada, e o modo watch a converteria de novo a
    cada volta ("nota_SEI_SEI.html", e assim por diante). O título cobre o nome escolhido
    com --saida; o nome cobre a saída com --corpo, que não tem título. Pedido pelo nome
    do arquivo, o HTML gerado ainda é convertido: a regra vale só para a varredura.
    """
    if arquivo.suffix.lower() not in EXTENSOES_HTML:
        return False
    if RE_NOME_DA_SAIDA.search(arquivo.name):
        return True
    try:
        with arquivo.open("rb") as f:
            inicio = f.read(1024)
    except OSError:
        return False
    return f"<title>{TITULO_DA_SAIDA}</title>".encode() in inicio


def converter_diretorio(
    diretorio: str | Path,
    outdir: str | Path | None = None,
    recursivo: bool = False,
    so_corpo: bool = False,
    max_nivel: int = 4,
    validar: bool = True,
    citacao_por_recuo: bool = False,
    omitir_cabecalho: bool = False,
    destinos_reservados: dict[Path, Path] | None = None,
) -> list[ResultadoConversao]:
    """Varre um diretório e converte todos os documentos compatíveis encontrados."""
    p_dir = Path(diretorio)
    if not p_dir.is_dir():
        raise NotADirectoryError(f"Caminho não é um diretório: {diretorio}")

    padrao = "**/*" if recursivo else "*"
    arquivos = sorted(f for f in p_dir.glob(padrao) if f.is_file() and entra_na_varredura(f))

    resultados = []
    if destinos_reservados is None:
        destinos_reservados = {}
    for arq in arquivos:
        destino_pasta = None
        if outdir is not None:
            relativo = arq.parent.relative_to(p_dir)
            destino_pasta = Path(outdir) / relativo

        res = converter_documento(
            caminho_entrada=arq,
            outdir=destino_pasta,
            so_corpo=so_corpo,
            max_nivel=max_nivel,
            validar=validar,
            citacao_por_recuo=citacao_por_recuo,
            omitir_cabecalho=omitir_cabecalho,
            destinos_reservados=destinos_reservados,
        )
        resultados.append(res)

    return resultados
