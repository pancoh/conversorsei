"""
odt_converter.py — Converte documentos do LibreOffice/OpenOffice (.odt) para blocos HTML SEI.

O ODT é um zip com o conteúdo em content.xml. A leitura usa só a biblioteca padrão
(zipfile e ElementTree), sem dependência nova, e devolve Markdown para o pipeline já
existente cuidar da estrutura institucional e da numeração do SEI.
"""
from __future__ import annotations

import re
import zipfile
import zlib
from dataclasses import dataclass, replace
from xml.etree import ElementTree

from conversorsei.docx_converter import AVISO_NOTAS
from conversorsei.entrada import FonteDocumento, abrir_binario, nome_da_fonte
from conversorsei.formatacao import (
    ESTILO_NUMERO_LITERAL,
    CitacaoPorRecuo,
    Formatacao,
    classe_sei_pelo_nome,
    fonte_predominante,
    indices_de_assinatura,
    linha_curta,
    numero_da_lista,
    paragrafos_entre_aspas,
    pode_ser_linha_de_assinatura,
)
from conversorsei.md_converter import (
    MARCA_QUEBRA_ODT,
    comeca_com_item,
    converter_texto_md_para_blocos,
    desescapar_markdown,
    escapar_markdown,
    linha_com_classe,
    linha_de_assinatura,
    marcar_colunas_mescladas,
    riscar_inteiro,
    texto_sem_marcacao,
)

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
}

MAX_NIVEL_TITULO = 4
LIMITE_HERANCA = 10

# O ODF escreve o espaço do nome do estilo como "_20_" ("Heading 1" vira "Heading_20_1").
# O nome interno costuma ser o inglês, mesmo em instalação em português.
RE_ESTILO_TITULO = re.compile(r"^(?:Heading|T[ií]tulo)(?:_20_| )(\d)$")
# O ODF codifica no nome interno do estilo o caractere que não pode ir num nome XML:
# "_5f_" é o sublinhado, "_20_" o espaço ("Texto_Ementa" vira "Texto_5f_Ementa")
RE_CODIGO_NO_NOME = re.compile(r"_([0-9a-fA-F]{2})_")
ALINHAMENTO_ODF = {
    "center": "center",
    "end": "right",
    "right": "right",
    "start": "left",
    "left": "left",
    "justify": "justify",
}

# (negrito, itálico, riscado) de um estilo de trecho
FormatoTrecho = tuple[bool, bool, bool]

# Medidas do ODF ("4cm", "1.5in", "113.4pt"). A porcentagem é relativa ao estilo pai e
# fica de fora: sem o valor absoluto, a regra não se aplica
RE_MEDIDA = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(cm|mm|in|pt|pc)\s*$")
CM_POR_UNIDADE = {"cm": 1.0, "mm": 0.1, "in": 2.54, "pt": 2.54 / 72, "pc": 2.54 / 6}
PT_POR_CM = 72 / 2.54


def _q(prefixo: str, nome: str) -> str:
    """Nome qualificado no formato que o ElementTree usa ({namespace}tag)."""
    return f"{{{NS[prefixo]}}}{nome}"


# Falhas ao ler um membro do pacote já aberto: ausente, CRC errado, fluxo truncado,
# compressão não suportada (deflate64) ou membro cifrado. Falha ao abrir o arquivo em si
# (inexistente, sem permissão) fica de fora e sobe com a causa real.
ERROS_DE_MEMBRO = (KeyError, zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError)


def _ler_opcional(z: zipfile.ZipFile, membro: str) -> bytes | None:
    """Conteúdo do membro do pacote, ou None se ele faltar ou estiver danificado.

    Um styles.xml com CRC errado não pode derrubar a conversão: o texto está no
    content.xml, e sem os estilos só as regras de formatação herdada deixam de valer.
    """
    try:
        return z.read(membro)
    except ERROS_DE_MEMBRO:
        return None


def _xml_opcional(bruto: bytes | None) -> ElementTree.Element | None:
    if not bruto:
        return None
    try:
        return ElementTree.fromstring(bruto)
    except ElementTree.ParseError:
        return None


def ler_xmls(caminho_odt: FonteDocumento) -> tuple[ElementTree.Element, ElementTree.Element | None]:
    """Raízes de content.xml (o texto) e de styles.xml (os estilos nomeados), numa só abertura.

    styles.xml é opcional: ausente, danificado ou malformado (gerador de terceiros), a
    formatação herdada dos estilos nomeados fica desconhecida e as regras que dependem
    dela não disparam. A conversão segue, como seguia quando styles.xml não era lido.
    """
    nome = nome_da_fonte(caminho_odt, "documento.odt")

    def invalido(e: Exception) -> RuntimeError:
        return RuntimeError(f"O arquivo {nome} não é um ODT válido: não foi possível ler o content.xml ({e}).")

    with abrir_binario(caminho_odt) as binario:
        try:
            pacote = zipfile.ZipFile(binario)
        except zipfile.BadZipFile as e:
            raise invalido(e) from e
        with pacote:
            try:
                bruto = pacote.read("content.xml")
            except ERROS_DE_MEMBRO as e:
                raise invalido(e) from e
            estilos = _ler_opcional(pacote, "styles.xml")
    try:
        raiz = ElementTree.fromstring(bruto)
    except ElementTree.ParseError as e:
        raise invalido(e) from e
    return raiz, _xml_opcional(estilos)


def mapear_heranca(raiz: ElementTree.Element) -> dict[str, str]:
    """Mapeia cada estilo automático ao estilo do qual ele herda.

    O LibreOffice nem sempre marca um título como <text:h>: quando o documento vem de
    outro formato, o título costuma ser um <text:p> cujo estilo automático (P1) herda de
    Heading_20_1. Sem seguir a herança, o título viraria parágrafo comum e o SEI perderia
    a numeração da seção.
    """
    heranca: dict[str, str] = {}
    for automaticos in raiz.iter(_q("office", "automatic-styles")):
        for estilo in automaticos.findall(_q("style", "style")):
            nome = estilo.get(_q("style", "name"))
            pai = estilo.get(_q("style", "parent-style-name"))
            if nome and pai:
                heranca[nome] = pai
    return heranca


def nivel_do_estilo(nome_estilo: str | None, heranca: dict[str, str]) -> int:
    """Nível de título do estilo (0 quando não é título), seguindo a cadeia de herança."""
    nome = nome_estilo
    for _ in range(LIMITE_HERANCA):
        if not nome:
            return 0
        m = RE_ESTILO_TITULO.match(nome)
        if m:
            return max(1, min(int(m.group(1)), MAX_NIVEL_TITULO))
        nome = heranca.get(nome)
    return 0


def _eh_riscado(valor: str | None) -> bool:
    """Valor de style:text-line-through-style que risca o texto ("none" não risca)."""
    return valor is not None and valor != "none"


def mapear_estilos(raiz: ElementTree.Element) -> dict[str, FormatoTrecho]:
    """Mapeia cada estilo automático para (negrito, itálico, riscado).

    O ODF guarda a formatação em estilos nomeados, e não no próprio texto: o
    <text:span> só aponta para o nome do estilo declarado em office:automatic-styles.
    """
    estilos: dict[str, FormatoTrecho] = {}
    for automaticos in raiz.iter(_q("office", "automatic-styles")):
        for estilo in automaticos.findall(_q("style", "style")):
            nome = estilo.get(_q("style", "name"))
            props = estilo.find(_q("style", "text-properties"))
            if not nome or props is None:
                continue
            negrito = props.get(_q("fo", "font-weight")) == "bold"
            italico = props.get(_q("fo", "font-style")) == "italic"
            riscado = _eh_riscado(props.get(_q("style", "text-line-through-style")))
            if negrito or italico or riscado:
                estilos[nome] = (negrito, italico, riscado)
    return estilos


def tabela_de_estilos(*raizes: ElementTree.Element | None) -> dict[str, ElementTree.Element]:
    """Todos os style:style dos XMLs, automáticos e nomeados, pelo nome interno."""
    tabela: dict[str, ElementTree.Element] = {}
    for raiz in raizes:
        if raiz is None:
            continue
        for estilo in raiz.iter(_q("style", "style")):
            nome = estilo.get(_q("style", "name"))
            if nome:
                tabela.setdefault(nome, estilo)
    return tabela


def _propriedade(nome: str, tabela: dict[str, ElementTree.Element], grupo: str, atributo: str) -> str | None:
    """Valor do atributo no estilo ou, se ausente, no estilo do qual ele herda.

    O LibreOffice grava no estilo automático só o que o parágrafo muda; o resto (o
    justificado de "Corpo de texto", por exemplo) vem do estilo pai, em styles.xml.
    """
    atual: str | None = nome
    for _ in range(LIMITE_HERANCA):
        estilo = tabela.get(atual or "")
        if estilo is None:
            return None
        props = estilo.find(_q("style", grupo))
        if props is not None and props.get(atributo) is not None:
            return props.get(atributo)
        atual = estilo.get(_q("style", "parent-style-name"))
    return None


def medida_em_cm(valor: str | None) -> float | None:
    """Converte uma medida do ODF para cm, ou None se não for uma medida absoluta."""
    m = RE_MEDIDA.match(valor or "")
    return float(m.group(1)) * CM_POR_UNIDADE[m.group(2)] if m else None


def tamanho_padrao(raiz_estilos: ElementTree.Element | None) -> float | None:
    """Fonte do estilo padrão de parágrafo (styles.xml), que vale quando nenhum estilo a define."""
    if raiz_estilos is None:
        return None
    for padrao in raiz_estilos.iter(_q("style", "default-style")):
        if padrao.get(_q("style", "family")) == "paragraph":
            props = padrao.find(_q("style", "text-properties"))
            cm = medida_em_cm(props.get(_q("fo", "font-size")) if props is not None else None)
            return round(cm * PT_POR_CM, 2) if cm is not None else None
    return None


def mapear_formatacao_paragrafos(
    tabela: dict[str, ElementTree.Element], padrao_pt: float | None = None
) -> dict[str, Formatacao]:
    """Mapeia cada estilo de parágrafo para a formatação efetiva, com a herança resolvida.

    Lê só o que as regras de formatacao.py usam: alinhamento, negrito, caixa alta,
    riscado, fonte e recuo. A fonte que nenhum estilo define é a do estilo padrão
    (`padrao_pt`), que vale também para o parágrafo sem estilo (chave ""). A fonte
    mudada só num trecho (<text:span>) não é lida.
    """
    formatos: dict[str, Formatacao] = {"": Formatacao(tamanho_pt=padrao_pt)}
    for nome, estilo in tabela.items():
        if estilo.get(_q("style", "family")) != "paragraph":
            continue

        def ler(grupo: str, prefixo: str, atributo: str, nome: str = nome) -> str | None:
            return _propriedade(nome, tabela, grupo, _q(prefixo, atributo))

        fonte_cm = medida_em_cm(ler("text-properties", "fo", "font-size"))
        formatos[nome] = Formatacao(
            alinhamento=ALINHAMENTO_ODF.get(ler("paragraph-properties", "fo", "text-align") or ""),
            tamanho_pt=round(fonte_cm * PT_POR_CM, 2) if fonte_cm is not None else padrao_pt,
            negrito=ler("text-properties", "fo", "font-weight") == "bold",
            maiusculas=ler("text-properties", "fo", "text-transform") == "uppercase",
            riscado=_eh_riscado(ler("text-properties", "style", "text-line-through-style")),
            recuo_esquerdo_cm=medida_em_cm(ler("paragraph-properties", "fo", "margin-left")) or 0.0,
        )
    return formatos


def nome_do_estilo_odf(nome: str) -> str:
    """Nome do estilo como o usuário o vê, sem os códigos do nome interno."""
    return RE_CODIGO_NO_NOME.sub(lambda m: chr(int(m.group(1), 16)), nome)


def classe_explicita(nome_estilo: str | None, heranca: dict[str, str]) -> str | None:
    """Classe SEI dada pelo nome do estilo do parágrafo ou de um estilo do qual ele herda."""
    nome = nome_estilo
    for _ in range(LIMITE_HERANCA):
        if not nome:
            return None
        classe = classe_sei_pelo_nome(nome_do_estilo_odf(nome))
        if classe:
            return classe
        nome = heranca.get(nome)
    return None


def _trechos(
    no: ElementTree.Element, estilos: dict[str, FormatoTrecho], negrito: bool = False, riscado: bool = False
):
    """Cada pedaço de texto do parágrafo com o negrito e o riscado que valem para ele."""
    yield no.text or "", negrito, riscado
    for filho in no:
        n, r = negrito, riscado
        if filho.tag == _q("text", "span"):
            n_span, _, r_span = estilos.get(filho.get(_q("text", "style-name")) or "", (False, False, False))
            n, r = n or n_span, r or r_span
        yield from _trechos(filho, estilos, n, r)
        yield filho.tail or "", negrito, riscado


def formatacao_do_paragrafo(
    no: ElementTree.Element, formatos: dict[str, Formatacao], estilos: dict[str, FormatoTrecho]
) -> Formatacao:
    """Formatação do parágrafo, completada pelos trechos.

    Negrito e riscado valem para o parágrafo quando valem para todo o texto: pelo estilo
    do parágrafo ou porque todos os trechos estão marcados.
    """
    base = formatos.get(no.get(_q("text", "style-name")) or "", formatos.get("", Formatacao()))
    marcas = [(n, r) for trecho, n, r in _trechos(no, estilos) if trecho.strip()]
    return replace(
        base,
        negrito=base.negrito or (bool(marcas) and all(n for n, _ in marcas)),
        riscado=base.riscado or (bool(marcas) and all(r for _, r in marcas)),
    )


def texto_do_no(
    no: ElementTree.Element, estilos: dict[str, FormatoTrecho], notas: list[tuple[str, str]] | None = None
) -> str:
    """Texto de um parágrafo com a marcação inline preservada em Markdown.

    Percorre os filhos em ordem porque negrito e itálico vivem em <text:span>, e os
    espaços repetidos, tabulações e quebras de linha têm elementos próprios no ODF.
    """
    partes: list[str] = [escapar_markdown(no.text or "")]

    for filho in no:
        tag = filho.tag
        conteudo = ""

        if tag == _q("text", "span"):
            negrito, italico, riscado = estilos.get(filho.get(_q("text", "style-name")) or "", (False, False, False))
            interno = texto_do_no(filho, estilos, notas)
            if interno.strip():
                if negrito:
                    interno = f"**{interno}**"
                if italico:
                    interno = f"*{interno}*"
                if riscado:
                    interno = f"~~{interno}~~"
            conteudo = interno
        elif tag == _q("text", "a"):
            rotulo = texto_do_no(filho, estilos, notas)
            href = filho.get(_q("xlink", "href")) or ""
            conteudo = f"[{rotulo}]({href})" if href else rotulo
        elif tag == _q("text", "s"):
            # Espaços repetidos são comprimidos pelo ODF num elemento com a contagem
            conteudo = " " * int(filho.get(_q("text", "c")) or 1)
        elif tag == _q("text", "tab"):
            conteudo = " "
        elif tag == _q("text", "line-break"):
            conteudo = MARCA_QUEBRA_ODT
        elif tag == _q("text", "note"):
            citacao = filho.find(_q("text", "note-citation"))
            corpo = filho.find(_q("text", "note-body"))
            numero = "".join(citacao.itertext()).strip() if citacao is not None else ""
            if not numero:
                numero = str(len(notas) + 1) if notas is not None else "?"
            if notas is not None and corpo is not None:
                conteudo_nota = " / ".join(
                    texto_do_no(p, estilos).strip() for p in corpo.iter(_q("text", "p"))
                ).strip()
                if conteudo_nota:
                    notas.append((numero, conteudo_nota))
            conteudo = escapar_markdown(f"[{numero}]")
        else:
            conteudo = texto_do_no(filho, estilos, notas)

        partes.append(conteudo)
        partes.append(escapar_markdown(filho.tail or ""))

    return "".join(partes)


def _linha_de_tabela(
    linha: ElementTree.Element, estilos: dict[str, FormatoTrecho], notas: list[tuple[str, str]] | None = None
) -> str:
    celulas = []
    for celula in linha.findall(_q("table", "table-cell")):
        textos = [texto_do_no(p, estilos, notas).strip() for p in celula.findall(_q("text", "p"))]
        # A barra vertical é o separador da tabela Markdown e não pode vir do conteúdo
        texto = " ".join(t for t in textos if t).replace("|", r"\|")
        celulas.extend(
            [marcar_colunas_mescladas(texto, _colunas_da_celula(celula))]
            * int(celula.get(_q("table", "number-columns-repeated")) or 1)
        )
    return "| " + " | ".join(celulas) + " |"


def _colunas_da_celula(celula: ElementTree.Element) -> int:
    return int(celula.get(_q("table", "number-columns-spanned")) or 1)


def tabela_para_markdown(
    tabela: ElementTree.Element, estilos: dict[str, FormatoTrecho], notas: list[tuple[str, str]] | None = None
) -> list[str]:
    """Converte uma table:table em linhas de tabela Markdown."""
    linhas = tabela.findall(_q("table", "table-row"))
    if not linhas:
        return []

    saida = [_linha_de_tabela(linhas[0], estilos, notas)]
    # Contadas no XML, e não no texto gerado: ali um "\|" do conteúdo pareceria coluna
    colunas = sum(
        _colunas_da_celula(celula) * int(celula.get(_q("table", "number-columns-repeated")) or 1)
        for celula in linhas[0].findall(_q("table", "table-cell"))
    )
    saida.append("| " + " | ".join(["---"] * max(colunas, 1)) + " |")
    for indice, linha in enumerate(linhas):
        repeticoes = int(linha.get(_q("table", "number-rows-repeated")) or 1) - (indice == 0)
        saida.extend(_linha_de_tabela(linha, estilos, notas) for _ in range(repeticoes))
    return saida


def _nivel_do_titulo(no: ElementTree.Element) -> int:
    try:
        nivel = int(no.get(_q("text", "outline-level")) or 1)
    except ValueError:
        nivel = 1
    return max(1, min(nivel, MAX_NIVEL_TITULO))


def fonte_do_corpo(corpo: ElementTree.Element, formatos: dict[str, Formatacao]) -> float | None:
    """Tamanho de fonte predominante no texto do documento, fora das tabelas."""
    amostras: list[tuple[float | None, int]] = []

    def visitar(no: ElementTree.Element) -> None:
        for filho in no:
            if filho.tag == _q("table", "table"):
                continue
            if filho.tag in (_q("text", "h"), _q("text", "p")):
                base = formatos.get(filho.get(_q("text", "style-name")) or "", formatos.get("", Formatacao()))
                amostras.append((base.tamanho_pt, len("".join(filho.itertext()).strip())))
            else:
                visitar(filho)

    visitar(corpo)
    return fonte_predominante(amostras)


def citacao_entre_aspas(
    corpo: ElementTree.Element, estilos: dict[str, FormatoTrecho], heranca: dict[str, str]
) -> set[ElementTree.Element]:
    """Parágrafos que estão numa citação entre aspas com mais de uma linha.

    Achados antes de montar o Markdown, porque a citação pode abrir num parágrafo e
    fechar vários depois. Segue a política de formatacao.paragrafos_entre_aspas, comum
    ao Word. Título, lista e tabela interrompem a citação: não passam por
    linha_com_classe e não teriam como sair como Citação.
    """
    elementos: list[ElementTree.Element] = []
    textos: list[str | None] = []

    def visitar(no: ElementTree.Element) -> None:
        for filho in no:
            if filho.tag in (_q("text", "h"), _q("text", "p")):
                texto = texto_do_no(filho, estilos).strip()
                if not texto:
                    continue
                titulo = filho.tag == _q("text", "h") or nivel_do_estilo(filho.get(_q("text", "style-name")), heranca)
                elementos.append(filho)
                textos.append(None if titulo else texto_sem_marcacao(texto))
            elif filho.tag in (_q("table", "table"), _q("text", "list")):
                elementos.append(filho)
                textos.append(None)
            else:
                visitar(filho)

    visitar(corpo)
    return {elementos[i] for i in paragrafos_entre_aspas(textos)}


@dataclass
class NumeracaoDaLista:
    """Como um nível de lista numerada escreve o número: formato, pontuação e início."""

    tipo: str = "1"
    prefixo: str = ""
    sufixo: str = "."
    inicio: int = 1

    def numero(self, posicao: int) -> str:
        return f"{self.prefixo}{numero_da_lista(posicao, self.tipo)}{self.sufixo}"


def mapear_listas(*raizes: ElementTree.Element | None) -> dict[str, dict[int, NumeracaoDaLista]]:
    """Mapeia cada estilo de lista para a numeração dos níveis que têm número.

    Nível com marcador, ou com o formato vazio (o LibreOffice não mostra número), fica de
    fora: o item segue como marcador.
    """
    listas: dict[str, dict[int, NumeracaoDaLista]] = {}
    for raiz in raizes:
        if raiz is None:
            continue
        for estilo in raiz.iter(_q("text", "list-style")):
            nome = estilo.get(_q("style", "name"))
            if not nome or nome in listas:
                continue
            niveis: dict[int, NumeracaoDaLista] = {}
            for nivel in estilo.findall(_q("text", "list-level-style-number")):
                tipo = nivel.get(_q("style", "num-format")) or ""
                if not tipo:
                    continue
                try:
                    numero_do_nivel = int(nivel.get(_q("text", "level")) or 1)
                    inicio = int(nivel.get(_q("text", "start-value")) or 1)
                except ValueError:
                    continue
                niveis[numero_do_nivel] = NumeracaoDaLista(
                    tipo=tipo if tipo in ("1", "a", "A", "i", "I") else "1",
                    prefixo=nivel.get(_q("style", "num-prefix")) or "",
                    sufixo=nivel.get(_q("style", "num-suffix")) or "",
                    inicio=inicio,
                )
            listas[nome] = niveis
    return listas


def converter_corpo(
    corpo: ElementTree.Element,
    estilos: dict[str, FormatoTrecho],
    heranca: dict[str, str],
    formatos: dict[str, Formatacao] | None = None,
    heranca_completa: dict[str, str] | None = None,
    citacao: CitacaoPorRecuo | None = None,
    notas: list[tuple[str, str]] | None = None,
    listas: dict[str, dict[int, NumeracaoDaLista]] | None = None,
) -> list[str]:
    """Percorre o corpo do documento devolvendo linhas de Markdown.

    `heranca` cobre só os estilos automáticos, e serve à detecção de títulos, como
    sempre serviu. `heranca_completa` inclui os estilos nomeados de styles.xml, para a
    classe explícita ser achada também quando vem de um estilo nomeado derivado.
    `citacao` conta os parágrafos com forma de citação e os converte quando pedido.
    `listas` traz, por estilo de lista, a numeração de cada nível (mapear_listas).

    As linhas centralizadas que fecham o documento viram o bloco de assinatura, pela
    mesma política do Word (formatacao.linhas_de_assinatura).
    """
    formatos = formatos or {}
    heranca_completa = heranca_completa or heranca
    linhas: list[str] = []
    # Um registro por parágrafo com texto ou tabela, na ordem, para achar o bloco de
    # assinatura: (índice da linha, candidata, formato, texto, texto da linha curta)
    registros: list[tuple[int, bool, Formatacao, str, str | None]] = []
    aspas = citacao_entre_aspas(corpo, estilos, heranca) if citacao is not None else set()

    def registrar(
        candidata: bool = False, formato: Formatacao | None = None, texto: str = "", curta: str | None = None
    ) -> None:
        registros.append((len(linhas) - 1, candidata, formato or Formatacao(), texto, curta))

    def paragrafo(filho: ElementTree.Element) -> tuple[str, Formatacao] | None:
        """Texto em Markdown e formatação de um text:p ou text:h, ou None se vazio."""
        texto = texto_do_no(filho, estilos, notas).strip()
        if not texto:
            return None
        formato = formatacao_do_paragrafo(filho, formatos, estilos)
        if formato.riscado:
            # Vale para item de lista e título também, que não passam por classe
            texto = riscar_inteiro(texto)
        return texto, formato

    def lista(no: ElementTree.Element, nivel: int, estilo_pai: str | None) -> None:
        """Itens de uma text:list, pelo estilo de lista do nível.

        O nível com número ("1.", "a)") sai com o número escrito no texto, como a lista
        numerada do HTML: o número é do texto, e não da numeração do SEI. O nível com
        marcador sai como item de lista, com dois espaços por nível, e os itens ficam
        colados: uma linha em branco entre eles quebraria a lista em várias.
        """
        estilo = no.get(_q("text", "style-name")) or estilo_pai
        numeracao = (listas or {}).get(estilo or "", {}).get(nivel + 1)
        posicao = numeracao.inicio if numeracao else 1
        for item in no:
            if item.tag not in (_q("text", "list-item"), _q("text", "list-header")):
                continue
            numerado = numeracao is not None and item.tag == _q("text", "list-item")
            try:
                posicao = int(item.get(_q("text", "start-value")) or posicao)
            except ValueError:
                pass
            primeiro = True
            for filho in item:
                if filho.tag == _q("text", "list"):
                    lista(filho, nivel + 1, estilo)
                    continue
                if filho.tag not in (_q("text", "h"), _q("text", "p")):
                    elemento(filho)
                    continue
                lido = paragrafo(filho)
                if lido is None:
                    continue
                texto = lido[0]
                if numerado and numeracao is not None:
                    if primeiro:
                        texto = f"{numeracao.numero(posicao)} {texto}"
                    linhas.append(linha_com_classe(texto, Formatacao(), ESTILO_NUMERO_LITERAL))
                    registrar()
                    linhas.append("")
                else:
                    linhas.append(f"{'  ' * min(nivel, 3)}- {texto}")
                    registrar()
                primeiro = False
            if numerado:
                posicao += 1
        if nivel == 0:
            linhas.append("")

    def elemento(filho: ElementTree.Element) -> None:
        tag = filho.tag
        if tag in (_q("text", "h"), _q("text", "p")):
            lido = paragrafo(filho)
            if lido is None:
                return
            texto, formato = lido
            if tag == _q("text", "h"):
                nivel = _nivel_do_titulo(filho)
            else:
                nivel = nivel_do_estilo(filho.get(_q("text", "style-name")), heranca)
            if nivel and (comeca_com_item(texto) or formato.riscado):
                # O número digitado decide o nível, como no Word ("1.1. Detalhamento"). O
                # título riscado sem número é parágrafo revogado, e o Markdown o faz Tachado
                linhas.append(f"{'#' * nivel} {texto}")
                registrar()
            elif nivel:
                # Título sem número: Item_Nivel do nível do título, como o Título do Word
                linhas.append(linha_com_classe(texto, formato, f"Item_Nivel{nivel}"))
                registrar()
            else:
                explicita = classe_explicita(filho.get(_q("text", "style-name")), heranca_completa)
                linhas.append(linha_com_classe(texto, formato, explicita, citacao, filho in aspas))
                visivel = desescapar_markdown(texto)
                sem_classe = not explicita and not comeca_com_item(texto)
                candidata = sem_classe and pode_ser_linha_de_assinatura(visivel, formato.alinhamento)
                registrar(candidata, formato, texto, visivel if sem_classe and linha_curta(visivel) else None)
            linhas.append("")
        elif tag == _q("table", "table"):
            md_tabela = tabela_para_markdown(filho, estilos, notas)
            if md_tabela:
                linhas.extend(md_tabela)
                registrar()
                linhas.append("")
        elif tag == _q("text", "list"):
            lista(filho, 0, None)
        else:
            visitar(filho)

    def visitar(no: ElementTree.Element) -> None:
        for filho in no:
            elemento(filho)

    visitar(corpo)
    for i in indices_de_assinatura([candidata for _, candidata, *_ in registros], [curta for *_, curta in registros]):
        indice, _, formato, texto, _ = registros[i]
        linhas[indice] = linha_de_assinatura(texto, formato)
    return linhas


def extrair_markdown_odt(
    caminho_odt: FonteDocumento, citacao: CitacaoPorRecuo | None = None, avisos: list[str] | None = None
) -> str:
    """Extrai o conteúdo de um .odt como Markdown."""
    nome = nome_da_fonte(caminho_odt, "documento.odt")
    raiz, raiz_estilos = ler_xmls(caminho_odt)
    if avisos is not None and any(True for _ in raiz.iter(_q("draw", "image"))):
        avisos.append("Imagens do ODT não foram incorporadas. Insira-as no SEI após conferir o original.")
    if avisos is not None and any(
        int(celula.get(_q("table", "number-rows-spanned")) or 1) > 1
        for celula in raiz.iter(_q("table", "table-cell"))
    ):
        avisos.append("Uma tabela tem células mescladas entre linhas. Confira a tabela no resultado e no SEI.")
    estilos = mapear_estilos(raiz)
    heranca = mapear_heranca(raiz)

    corpo = raiz.find(f"{_q('office', 'body')}/{_q('office', 'text')}")
    if corpo is None:
        raise RuntimeError(f"O arquivo {nome} não tem corpo de texto.")

    tabela = tabela_de_estilos(raiz, raiz_estilos)
    heranca_completa = {
        nome: pai for nome, estilo in tabela.items() if (pai := estilo.get(_q("style", "parent-style-name")))
    }
    formatos = mapear_formatacao_paragrafos(tabela, tamanho_padrao(raiz_estilos))
    if citacao is not None:
        citacao.fonte_do_corpo = fonte_do_corpo(corpo, formatos)
    notas: list[tuple[str, str]] = []
    listas = mapear_listas(raiz, raiz_estilos)
    markdown = "\n".join(
        converter_corpo(corpo, estilos, heranca, formatos, heranca_completa, citacao, notas, listas)
    )
    if notas:
        if avisos is not None:
            avisos.append(AVISO_NOTAS)
        markdown += "\n\n## Notas\n\n" + "\n\n".join(f"Nota {numero}: {texto}" for numero, texto in notas)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    if not markdown:
        raise RuntimeError(
            f"Nenhum texto foi encontrado em {nome}: o documento pode estar vazio "
            "ou conter apenas imagens."
        )
    return markdown + "\n"


def converter_odt_para_blocos(
    caminho_odt: FonteDocumento,
    max_nivel: int = 4,
    citacao: CitacaoPorRecuo | None = None,
    avisos: list[str] | None = None,
) -> list[str]:
    """Converte um arquivo ODT para blocos HTML SEI."""
    markdown = extrair_markdown_odt(caminho_odt, citacao=citacao, avisos=avisos)
    # Sem `citacao`: as duas regras já passaram por linha_com_classe, e o parágrafo
    # sugerido e deixado como texto seria contado de novo pela regra das aspas
    return converter_texto_md_para_blocos(markdown, max_nivel=max_nivel, extraido=True)


def converter_odt_para_html(caminho_odt: FonteDocumento, max_nivel: int = 4) -> str:
    """Converte arquivo ODT e retorna o HTML do corpo consolidado."""
    return "\n".join(converter_odt_para_blocos(caminho_odt, max_nivel=max_nivel))
