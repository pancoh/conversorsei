"""
docx_converter.py — Converte arquivos Word (.docx) para blocos e HTML no padrão do SEI.
"""
from __future__ import annotations

import base64
import html as htmlmod
import re
import weakref
from typing import Any

from docx import Document

# docx.Document é a fábrica; o tipo do objeto vive em docx.document
from docx.document import Document as DocumentoWord
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from conversorsei.entrada import FonteDocumento, abrir_binario
from conversorsei.formatacao import (
    CLASSE_ASSINATURA,
    ESTILO_NUMERO_LITERAL,
    RE_MARCA_ASSINATURA,
    CitacaoPorRecuo,
    Formatacao,
    classe_de_tabela_por_formatacao,
    classe_por_formatacao,
    classe_sei_pelo_nome,
    fonte_predominante,
    indices_de_assinatura,
    linha_curta,
    maior_tamanho,
    paragrafos_entre_aspas,
    pode_ser_linha_de_assinatura,
    texto_em_maiusculas,
)

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

# Largura, em px, que uma imagem com a largura toda da área de texto do Word recebe no SEI.
# Sem largura no <img>, o editor do SEI mostrava a foto no tamanho original (1.600 px de
# uma câmera), muito maior que a página. 800 px ficou bom colado no SEI
LARGURA_DA_PAGINA_SEI_PX = 800
EMU_POR_TWIP = 635

RE_NUM_DECIMAL = re.compile(r"^\s*\d+(\.\d+)*\.?\s*[-–—]?\s+")
RE_NUM_ROMANO = re.compile(r"^\s*[IVXLCDM]+\s*[-–—.)]\s+")
RE_NUM_LETRA = re.compile(r"^\s*[a-z]\s*[).]\s+")

# Detecção de item numerado digitado (1., 1.1., 3.1, 3.1.1. ...) para mapear a Item_NivelN
RE_ITEM_INICIO = re.compile(r"^\s*(\d+(?:\.\d+)*)(\.)?\s+\S")
# Remove o número digitado do início mesmo envolto por tags de abertura. O grupo final
# recolhe as tags de fechamento que o Word deixa entre o número e o texto quando só a
# numeração está em negrito ("<strong>1.</strong> ASSUNTO"): sem ele o número sobrevive
# e o SEI, que renumera sozinho, mostra "1. 1. ASSUNTO".
RE_STRIP_ITEM = re.compile(r"^((?:<[^/!][^>]*>\s*)*)\d+(?:\.\d+)*\.?\s*[-–—]?((?:\s*</[^>]+>)*)\s+")
# Par de tags de formatação sem nada dentro, como o "<strong></strong>" que sobra quando
# só o número estava em negrito. Sem espaço dentro: "<strong> </strong>" separa palavras
RE_TAG_VAZIA = re.compile(r"<(strong|em|u|s|span)(?:\s[^>]*)?></\1>")
# Converte links Markdown literais residuais [texto](url) em <a>. O endereço pode ter um
# par de parênteses, como os da Wikipédia ("..._(direito)")
RE_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)")
# Esquemas que viram link na saída. "javascript:" e "data:" executariam código ou abririam
# conteúdo arbitrário no clique, dentro do SEI; endereço sem esquema (relativo) fica
ESQUEMAS_DE_LINK = frozenset({"http", "https", "mailto", "tel", "ftp"})
RE_ESQUEMA = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")


def endereco_seguro(href: str | None) -> str | None:
    """O endereço, se ele pode virar link na saída; None quando o esquema não é permitido.

    O navegador ignora espaços e caracteres de controle no esquema ("java\\tscript:"), e
    por isso eles saem antes da conferência.
    """
    endereco = (href or "").strip()
    if not endereco:
        return None
    esquema = RE_ESQUEMA.match(re.sub(r"[\x00-\x20]", "", endereco))
    if esquema and esquema.group(1).lower() not in ESQUEMAS_DE_LINK:
        return None
    return endereco

MAX_NIVEL_PADRAO = 4

# Classe institucional aplicada aos <li> de listas com marcadores
CLASSE_ITEM_LISTA = "Texto_Justificado"

# Um estilo do Word herda de outro; o limite só protege contra herança circular
LIMITE_HERANCA_ESTILO = 10
# O recuo do Word vem em twips (1/1440 de polegada)
TWIPS_POR_CM = 1440 / 2.54



def profundidade_item(texto: str) -> int:
    """Profundidade de um item numerado digitado (1 para '1.', 2 para '1.1'/'3.1', ...).

    Retorna 0 quando não há numeração de item no início. Um número isolado sem ponto
    final (ex.: um ano '2026 ...') não é considerado item.
    """
    m = RE_ITEM_INICIO.match(texto or "")
    if not m:
        return 0
    grupos = m.group(1)
    ponto_final = m.group(2) == "."
    n = grupos.count(".") + 1
    if n == 1 and not ponto_final:
        return 0
    return n


def item_digitado(p: Paragraph, texto: str) -> int:
    """profundidade_item do parágrafo, ou 0 quando o número veio de uma lista numerada.

    O leitor de HTML escreve o número da lista no texto e marca o parágrafo com
    ESTILO_NUMERO_LITERAL: o número é do texto, e não um item da numeração do SEI.
    """
    return 0 if nome_do_estilo(p) == ESTILO_NUMERO_LITERAL else profundidade_item(texto)


# Um "1." no início do parágrafo pode ser título de seção ("1. ASSUNTO") ou parágrafo
# numerado de texto corrido ("1. Trata-se da necessidade de..."), que são coisas visualmente
# muito diferentes no SEI: Item_Nivel1 aplica caixa alta, negrito e tarja cinza.
LIMITE_PALAVRAS_TITULO = 8
LIMITE_PALAVRAS_FRASE = 5


def parece_texto_corrido(texto: str) -> bool:
    """Indica se o texto após a numeração é um parágrafo, e não um título de seção.

    Título de seção costuma ser curto, sem pontuação interna e sem ponto final
    ("1. ASSUNTO", "3. Conclusão"). Parágrafo costuma ser uma frase pontuada.
    Erros isolados não desalinham o documento: a classe final é decidida pela
    convenção majoritária, em convencao_de_numeracao().
    """
    corpo = RE_NUM_DECIMAL.sub("", (texto or "").strip(), count=1).strip()
    if not corpo:
        return False
    if corpo.isupper():
        return False

    palavras = corpo.split()
    if len(palavras) > LIMITE_PALAVRAS_TITULO:
        return True
    if corpo.endswith("."):
        return "," in corpo or ";" in corpo or len(palavras) > LIMITE_PALAVRAS_FRASE
    return False


def _md_links(s: str) -> str:
    """Converte links Markdown literais remanescentes em âncoras HTML."""
    return RE_MD_LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)


def esc(t: str) -> str:
    return htmlmod.escape(t, quote=False)


def alinhamento(p: Paragraph) -> str | None:
    """Alinhamento efetivo do parágrafo ('center','right','justify','left' ou None)."""
    try:
        a = p.alignment
    except Exception:
        a = None
    estilo = estilo_do_paragrafo(p)
    if a is None and estilo is not None:
        try:
            a = estilo.paragraph_format.alignment
        except Exception:
            a = None
    if a is None:
        return None
    s = str(a)
    for k in ("CENTER", "RIGHT", "JUSTIFY", "LEFT"):
        if k in s:
            return k.lower()
    return None


def _estilos_em_cadeia(estilo):
    """O estilo e os estilos de que ele herda, do mais específico ao mais geral."""
    for _ in range(LIMITE_HERANCA_ESTILO):
        if estilo is None:
            return
        yield estilo
        estilo = estilo.base_style


# Cadeia de estilos por (tipo, id), guardada por documento. Cada consulta de estilo no
# python-docx é uma busca no styles.xml; sem o cache, ela se repetiria a cada run.
_CACHE_ESTILOS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _cadeia_de_estilos(parte, style_id: str | None, tipo) -> list:
    cache = _CACHE_ESTILOS.setdefault(parte, {})
    chave = (tipo, style_id)
    if chave not in cache:
        cache[chave] = list(_estilos_em_cadeia(parte.get_style(style_id, tipo)))
    return cache[chave]


def _estilos_do_paragrafo(p: Paragraph) -> list:
    return _cadeia_de_estilos(p.part, p._p.style, WD_STYLE_TYPE.PARAGRAPH)


def estilo_do_paragrafo(p: Paragraph):
    """Estilo do parágrafo (o padrão do documento, quando ele não indica nenhum).

    Substitui o p.style do python-docx, que percorre a lista inteira de estilos a cada
    leitura. Lido cerca de dez vezes por parágrafo, ele tomava mais de 90% do tempo de
    conversão de um documento longo. Aqui a consulta passa pelo cache da cadeia.
    """
    cadeia = _estilos_do_paragrafo(p)
    return cadeia[0] if cadeia else None


def nome_do_estilo(p: Paragraph) -> str | None:
    estilo = estilo_do_paragrafo(p)
    return estilo.name if estilo is not None else None


def _tamanho_padrao(parte) -> float | None:
    """Tamanho de fonte do docDefaults, que vale quando nem o run nem os estilos o definem.

    O python-docx não o inclui na cadeia de estilos. Sem ele, um corpo que deixa a fonte
    no padrão do documento ficaria sem tamanho conhecido, e a citação em 10 pt ao lado
    dele não teria com o que ser comparada.
    """
    cache = _CACHE_ESTILOS.setdefault(parte, {})
    if "tamanho_padrao" not in cache:
        caminho = "/".join(qn(t) for t in ("w:docDefaults", "w:rPrDefault", "w:rPr", "w:sz"))
        try:
            sz = parte.styles.element.find(caminho)
            cache["tamanho_padrao"] = int(sz.get(qn("w:val"))) / 2 if sz is not None else None
        except (AttributeError, TypeError, ValueError):
            cache["tamanho_padrao"] = None
    return cache["tamanho_padrao"]


def _recuo_esquerdo_cm(p: Paragraph) -> float:
    """Recuo esquerdo efetivo em cm: o do parágrafo ou, se ausente, o do estilo.

    Lê w:left e w:start: o Word atual grava w:start, que o python-docx não expõe.
    """
    for pPr in [p._p.pPr] + [estilo.element.pPr for estilo in _estilos_do_paragrafo(p)]:
        ind = pPr.find(qn("w:ind")) if pPr is not None else None
        valor = None if ind is None else ind.get(qn("w:left")) or ind.get(qn("w:start"))
        if valor is None:
            continue
        try:
            return int(valor) / TWIPS_POR_CM
        except ValueError:
            return 0.0
    return 0.0


def _fontes_do_run(run, estilos_do_paragrafo: list) -> list:
    """Fontes que valem para o run, da mais específica à mais geral.

    O python-docx só expõe a formatação direta do run. Um título do modelo que é
    negrito pelo estilo teria o run com bold None, e passaria por texto comum. Run sem
    estilo de caractere próprio usa o padrão, que não formata nada, e não é consultado.
    """
    estilo_run = run._r.style
    estilos_run = _cadeia_de_estilos(run.part, estilo_run, WD_STYLE_TYPE.CHARACTER) if estilo_run else []
    return [run.font, *(e.font for e in estilos_run), *(e.font for e in estilos_do_paragrafo)]


def _primeiro_definido(fontes: list, ler):
    for fonte in fontes:
        valor = ler(fonte)
        if valor is not None:
            return valor
    return None


def _elementos_visiveis(no):
    """Abre os contêineres que mostram texto no Word sem incluir revisões excluídas.

    O python-docx não expõe runs de inserções, controles de conteúdo e campos simples
    em ``p.runs`` ou ``p.text``. Esses elementos precisam entrar na mesma ordem do XML.
    """
    for filho in no.iterchildren():
        if filho.tag in (qn("w:r"), qn("w:hyperlink")):
            yield filho
        elif filho.tag == qn("w:sdt"):
            conteudo = filho.find(qn("w:sdtContent"))
            if conteudo is not None:
                yield from _elementos_visiveis(conteudo)
        elif filho.tag in (qn("w:ins"), qn("w:moveTo"), qn("w:fldSimple"), qn("w:smartTag"), qn("w:customXml")):
            yield from _elementos_visiveis(filho)


def _filhos_visiveis(no, tags: tuple[str, ...]):
    """Filhos com uma das tags, inclusive os que estão dentro de controles de conteúdo.

    O Word envolve parágrafos, tabelas, linhas e células em w:sdt, w:ins e w:customXml.
    Quem percorre só os filhos diretos perde esse conteúdo sem aviso.
    """
    for filho in no.iterchildren():
        if filho.tag in tags:
            yield filho
        elif filho.tag == qn("w:sdt"):
            conteudo = filho.find(qn("w:sdtContent"))
            if conteudo is not None:
                yield from _filhos_visiveis(conteudo, tags)
        elif filho.tag in (qn("w:ins"), qn("w:moveTo"), qn("w:customXml")):
            yield from _filhos_visiveis(filho, tags)


def _blocos_visiveis(no):
    """Parágrafos e tabelas do corpo ou de uma célula, inclusive em controles de conteúdo."""
    return _filhos_visiveis(no, (qn("w:p"), qn("w:tbl")))


def _runs_visiveis(p: Paragraph) -> list:
    """Todos os runs exibidos, inclusive os de contêineres e hiperlinks, na ordem do XML."""
    from docx.text.run import Run

    runs: list[Run] = []
    for filho in _elementos_visiveis(p._p):
        if filho.tag == qn("w:r"):
            elementos = [filho]
        elif filho.tag == qn("w:hyperlink"):
            elementos = filho.findall(qn("w:r"))
        else:
            continue
        runs.extend(Run(el, p) for el in elementos)
    return runs


def _runs_com_texto(p: Paragraph) -> list:
    """Runs com texto visível: os só de espaço não contam para a formatação do parágrafo."""
    return [run for run in _runs_visiveis(p) if (run.text or "").strip()]


def texto_visivel(p: Paragraph) -> str:
    """Lê o texto exibido no Word para classificar também parágrafos em contêineres.

    Inclui os runs só de espaço ou tab: sem eles, "1." e "ASSUNTO" em runs separados
    virariam "1.ASSUNTO", e o número digitado deixaria de ser reconhecido.

    Fica guardado por parágrafo, no cache do documento: a classificação lê o texto de
    cada parágrafo quatro ou cinco vezes, e montá-lo run a run pesa num documento longo.
    O documento não muda durante a conversão, então o texto guardado continua valendo.
    """
    textos = _CACHE_ESTILOS.setdefault(p.part, {}).setdefault("textos", {})
    texto = textos.get(p._p)
    if texto is None:
        texto = textos[p._p] = "".join(run.text for run in _runs_visiveis(p))
    return texto


def _fundo_cinza(p: Paragraph) -> bool:
    """Indica se o parágrafo tem sombreamento cinza (r, g e b próximos, nem branco nem preto)."""
    elementos = [p._p.pPr] + [estilo.element.pPr for estilo in _estilos_do_paragrafo(p)]
    for pPr in elementos:
        shd = pPr.find(qn("w:shd")) if pPr is not None else None
        if shd is None:
            continue
        cor = (shd.get(qn("w:fill")) or "").lower()
        if not re.fullmatch(r"[0-9a-f]{6}", cor):
            return False
        r, g, b = (int(cor[i : i + 2], 16) for i in (0, 2, 4))
        return max(r, g, b) - min(r, g, b) <= 16 and 128 <= (r + g + b) / 3 <= 245
    return False


def _letras_espacadas(run) -> bool:
    """Espaçamento entre caracteres positivo (w:spacing no run, em vigésimos de ponto)."""
    rPr = run._r.rPr
    spacing = rPr.find(qn("w:spacing")) if rPr is not None else None
    try:
        return spacing is not None and int(spacing.get(qn("w:val")) or 0) > 0
    except ValueError:
        return False


def formatacao_de_celula(p: Paragraph, alin: str | None) -> Formatacao:
    """Só o que a regra de tabela usa (alinhamento e fonte), sem o custo do resto."""
    estilos = _estilos_do_paragrafo(p)
    return Formatacao(alinhamento=alin, tamanho_pt=_tamanho_pt([_fontes_do_run(r, estilos) for r in _runs_com_texto(p)]))


def _tamanho_pt(fontes_por_run: list[list], padrao: float | None = None) -> float | None:
    tamanhos = [_primeiro_definido(fontes, lambda f: f.size) for fontes in fontes_por_run]
    return maior_tamanho([t.pt if t is not None else padrao for t in tamanhos])


def fonte_do_corpo(doc: DocumentoWord) -> float | None:
    """Tamanho de fonte predominante no texto do documento, fora das tabelas."""
    amostras = []
    for filho in _blocos_visiveis(doc.element.body):
        if filho.tag != qn("w:p"):
            continue
        p = Paragraph(filho, doc)
        runs = _runs_com_texto(p)
        if runs:
            estilos = _estilos_do_paragrafo(p)
            tamanho = _tamanho_pt([_fontes_do_run(r, estilos) for r in runs], _tamanho_padrao(p.part))
            amostras.append((tamanho, sum(len(r.text) for r in runs)))
    return fonte_predominante(amostras)


def formatacao_do_paragrafo(p: Paragraph, alin: str | None) -> Formatacao:
    """Traduz a formatação do parágrafo do Word para o vocabulário de formatacao.py."""
    runs = _runs_com_texto(p)
    if not runs:
        return Formatacao(alinhamento=alin)
    estilos = _estilos_do_paragrafo(p)
    fontes_por_run = [_fontes_do_run(r, estilos) for r in runs]

    def todos(ler) -> bool:
        return all(bool(_primeiro_definido(fontes, ler)) for fontes in fontes_por_run)

    return Formatacao(
        alinhamento=alin,
        # O padrão do documento entra aqui, e não na célula: lá ele faria toda tabela de um
        # documento em 10 pt virar Tabela_Texto_10
        tamanho_pt=_tamanho_pt(fontes_por_run, _tamanho_padrao(p.part)),
        negrito=todos(lambda f: f.bold),
        maiusculas=texto_em_maiusculas(texto_visivel(p)) or todos(lambda f: f.all_caps),
        riscado=todos(lambda f: f.strike),
        fundo_cinza=_fundo_cinza(p),
        letras_espacadas=all(_letras_espacadas(r) for r in runs),
        recuo_esquerdo_cm=_recuo_esquerdo_cm(p),
    )


def formato_lista_xml(doc: DocumentoWord, p: Paragraph) -> tuple[str | None, int | None]:
    """Inspeciona numbering.xml para descobrir o numFmt real de listas no Word."""
    pPr = p._p.pPr
    # Os filhos de numPr são gerados em tempo de execução e não aparecem nos stubs
    numPr = pPr.numPr if pPr is not None else None
    if numPr is None or numPr.numId is None:  # type: ignore[attr-defined]
        return None, None
    num_id = str(numPr.numId.val)  # type: ignore[attr-defined]
    ilvl = str(numPr.ilvl.val if numPr.ilvl is not None else 0)  # type: ignore[attr-defined]
    # numId 0 é como o Word tira a numeração herdada do estilo: o parágrafo não é item
    if num_id == "0":
        return None, None
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return "decimal", int(ilvl)
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    abstract_id = None
    for num in numbering.findall(f"{W}num"):
        if num.get(f"{W}numId") == num_id:
            ab = num.find(f"{W}abstractNumId")
            if ab is not None:
                abstract_id = ab.get(f"{W}val")
            break
    if abstract_id is not None:
        for absnum in numbering.findall(f"{W}abstractNum"):
            if absnum.get(f"{W}abstractNumId") == abstract_id:
                for lvl in absnum.findall(f"{W}lvl"):
                    if lvl.get(f"{W}ilvl") == ilvl:
                        fmt = lvl.find(f"{W}numFmt")
                        if fmt is not None:
                            return fmt.get(f"{W}val"), int(ilvl)
    return "decimal", int(ilvl)


def remover_tags_vazias(html: str) -> str:
    """Tira os pares de tags que ficaram vazios, inclusive os aninhados.

    Repete até estabilizar: "<span><strong></strong></span>" só fica vazio por fora
    depois que o par de dentro sai.
    """
    anterior = None
    while anterior != html:
        anterior, html = html, RE_TAG_VAZIA.sub("", html)
    return html


def nivel_do_marcador(doc: DocumentoWord, p: Paragraph) -> int:
    """Nível do item de marcador na lista, de 0 a 3.

    Vem do ilvl da numeração do parágrafo ou do número no nome do estilo ("List Bullet 2",
    que é como o Markdown grava o subitem). O recuo em cm não serve: o recuo padrão de uma
    lista de primeiro nível (1,27 cm) passaria por subitem e deslocaria a lista no SEI.
    """
    _, ilvl = formato_lista_xml(doc, p)
    if ilvl is None:
        m = re.search(r"list bullet\s*(\d)", (nome_do_estilo(p) or "").lower())
        ilvl = int(m.group(1)) - 1 if m else 0
    return max(0, min(ilvl, 3))


def classe_do_paragrafo(
    doc: DocumentoWord,
    p: Paragraph,
    dentro_tabela: bool = False,
    primeira_linha: bool = False,
    nivel_base_lista: int = 2,
    convencao: str = "titulos",
    citacao: CitacaoPorRecuo | None = None,
) -> str:
    """Decide a classe SEI institucional do parágrafo.

    `nivel_base_lista` define o Item_Nivel de uma lista numerada do Word no ilvl 0.
    Vale 2 quando o documento já tem títulos (a lista é subitem) e 1 quando não tem,
    evitando um documento cuja numeração começa em "0.1". `citacao` conta os parágrafos
    com forma de citação e os converte quando pedido.
    """
    nome_estilo = nome_do_estilo(p) or ""
    ne = nome_estilo.lower()
    alin = alinhamento(p)

    if dentro_tabela:
        pequena = classe_de_tabela_por_formatacao(formatacao_de_celula(p, alin), primeira_linha)
        if pequena:
            return pequena
        if primeira_linha:
            return "Tabela_Texto_Centralizado"
        if alin == "center":
            return "Tabela_Texto_Centralizado"
        if alin == "right":
            return "Tabela_Texto_Alinhado_Direita"
        return "Tabela_Texto_Alinhado_Esquerda"

    # Títulos do Word -> níveis numerados do SEI
    m = re.search(r"(heading|t[ií]tulo)\s*(\d)", ne)
    if m:
        nivel = min(int(m.group(2)), 4)
        return f"Item_Nivel{nivel}"

    # Listas de marcadores do Word (estilo List Bullet)
    if "list bullet" in ne:
        return "__BULLET__"

    # Citações
    if "quote" in ne or "citação" in ne or "citacao" in ne:
        return "Citação"

    # Listas do Word
    fmt, ilvl = formato_lista_xml(doc, p)
    if fmt:
        if fmt == "lowerLetter":
            return "Item_Alinea_Letra"
        if fmt in ("upperRoman", "lowerRoman"):
            return "Item_Inciso_Romano"
        if fmt == "bullet":
            return "__BULLET__"
        nivel = max(min(nivel_base_lista + (ilvl or 0), 4), 1)
        if convencao == "paragrafos":
            # Documento de parágrafos numerados: sem caixa alta nem tarja cinza
            return f"Paragrafo_Numerado_Nivel{min(nivel, 3)}"
        return f"Item_Nivel{nivel}"

    # Formatação que corresponde a uma classe própria do SEI (riscado, fundo cinza, etc.)
    formatacao = formatacao_do_paragrafo(p, alin)
    por_formatacao = classe_por_formatacao(formatacao)
    if por_formatacao:
        return por_formatacao
    if citacao is not None:
        por_recuo = citacao.classe(formatacao, texto_visivel(p))
        if por_recuo:
            return por_recuo

    # Alinhamento explícito
    if alin == "center":
        return "Texto_Centralizado"
    if alin == "right":
        return "Texto_Alinhado_Direita"
    if alin == "left":
        return "Texto_Alinhado_Esquerda"

    # Recuo de primeira linha
    try:
        fi = p.paragraph_format.first_line_indent
        if fi is not None and fi.pt > 8:
            return "Texto_Justificado_Recuo_Primeira_Linha"
    except Exception:
        pass

    return "Texto_Justificado"


def dimensoes_em_pixels(blob: bytes) -> tuple[int, int] | None:
    """Largura e altura em pixels de uma imagem PNG, JPEG ou GIF, lidas do cabeçalho.

    Serve só para não ampliar a imagem além do tamanho original. Lê o cabeçalho à mão
    para não depender de uma biblioteca de imagens, que pesaria no carregamento da página.
    Formato desconhecido ou cabeçalho estranho devolve None.
    """
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")
    if blob[:6] in (b"GIF87a", b"GIF89a") and len(blob) >= 10:
        return int.from_bytes(blob[6:8], "little"), int.from_bytes(blob[8:10], "little")
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(blob):
            if blob[i] != 0xFF:
                return None
            marca = blob[i + 1]
            if marca == 0xFF:
                i += 1
                continue
            tamanho = int.from_bytes(blob[i + 2 : i + 4], "big")
            # SOF0 a SOF15, menos DHT (C4), JPG (C8) e DAC (CC), trazem as dimensões
            if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
                altura = int.from_bytes(blob[i + 5 : i + 7], "big")
                largura = int.from_bytes(blob[i + 7 : i + 9], "big")
                return (largura, altura) if largura and altura else None
            i += 2 + tamanho
    return None


def dimensoes_no_sei(doc: DocumentoWord, blip, blob: bytes) -> tuple[int, int] | None:
    """Largura e altura, em px, com que a imagem deve aparecer no SEI.

    A largura guarda a proporção que a imagem tem na página do Word: a fração da área de
    texto que ela ocupa (wp:extent) vezes LARGURA_DA_PAGINA_SEI_PX. Assim, a foto na
    largura da página fica perto de 800 px e um logotipo pequeno continua pequeno. Nunca
    passa do tamanho original, para não ampliar a imagem. A altura segue a proporção.
    Sem medida no Word, vale o tamanho original limitado à largura da página; sem nenhuma
    medida, devolve None e o <img> sai sem tamanho, como antes.
    """
    original = dimensoes_em_pixels(blob)
    desenho = blip.getparent()
    while desenho is not None and desenho.tag not in (f"{{{NS_WP}}}inline", f"{{{NS_WP}}}anchor"):
        desenho = desenho.getparent()
    extent = desenho.find(f"{{{NS_WP}}}extent") if desenho is not None else None
    try:
        cx, cy = int(extent.get("cx")), int(extent.get("cy"))  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        cx = cy = 0

    if cx > 0 and cy > 0:
        area = _area_de_texto(doc)
        fracao = min(1.0, cx / (area * EMU_POR_TWIP)) if area else 1.0
        largura = round(fracao * LARGURA_DA_PAGINA_SEI_PX)
        proporcao = cy / cx
    elif original:
        largura = min(original[0], LARGURA_DA_PAGINA_SEI_PX)
        proporcao = original[1] / original[0]
    else:
        return None
    if original:
        largura = min(largura, original[0])
    largura = max(1, largura)
    return largura, max(1, round(largura * proporcao))


# Notas de rodapé: a chamada vira "[1]" no texto e a nota vai para uma seção "Notas" no
# fim, como no leitor de ODT. O SEI não tem nota de rodapé, e descartá-la perdia conteúdo
AVISO_NOTAS = (
    "As notas de rodapé foram para o fim do texto, na seção Notas, com a chamada entre colchetes "
    "([1], [2]). Confira antes de colar."
)
REL_NOTAS_DE_RODAPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"


def _texto_da_nota(nota) -> str:
    """Texto de uma w:footnote, com os parágrafos separados por " / ", como no ODT."""
    paragrafos = []
    for p in nota.iter(qn("w:p")):
        partes = []
        for el in p.iter(qn("w:t"), qn("w:tab"), qn("w:br")):
            partes.append(el.text or "" if el.tag == qn("w:t") else " ")
        texto = re.sub(r"\s+", " ", "".join(partes)).strip()
        if texto:
            paragrafos.append(texto)
    return " / ".join(paragrafos)


def notas_de_rodape(doc: DocumentoWord) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Número de cada chamada (pelo id da nota) e o texto das notas, na ordem do documento.

    O Word numera as notas pela ordem em que aparecem, e não pelo id, que pode pular.
    Calculado uma vez por documento.
    """
    cache = _CACHE_ESTILOS.setdefault(doc.part, {})
    if "notas" not in cache:
        textos: dict[str, str] = {}
        for rel in doc.part.rels.values():
            if rel.reltype == REL_NOTAS_DE_RODAPE and not rel.is_external:
                raiz = parse_xml(rel.target_part.blob)
                for nota in raiz.iter(qn("w:footnote")):
                    if nota.get(qn("w:type")) in (None, "normal"):
                        textos[nota.get(qn("w:id")) or ""] = _texto_da_nota(nota)
        numeros: dict[str, int] = {}
        notas: list[tuple[int, str]] = []
        for chamada in doc.element.body.iter(qn("w:footnoteReference")):
            id_nota = chamada.get(qn("w:id")) or ""
            if id_nota in numeros or id_nota not in textos:
                continue
            numeros[id_nota] = len(numeros) + 1
            notas.append((numeros[id_nota], textos[id_nota]))
        cache["notas"] = (numeros, notas)
    return cache["notas"]


def blocos_das_notas(doc: DocumentoWord) -> list[str]:
    """A seção "Notas" do fim do documento, no mesmo formato da que sai do ODT."""
    _, notas = notas_de_rodape(doc)
    if not notas:
        return []
    return ['<p class="Texto_Centralizado"><strong>Notas</strong></p>'] + [
        f'<p class="Texto_Justificado">Nota {numero}: {esc(texto)}</p>' for numero, texto in notas if texto
    ]


def run_para_html(doc: DocumentoWord, run_el, p: Paragraph, estilos_do_paragrafo: list | None = None) -> str:
    """Converte um <w:r> em HTML inline (negrito, itálico, imagens Base64, etc.)."""
    from docx.text.run import Run

    run = Run(run_el, p)
    partes: list[str] = []

    # Imagens no run -> base64
    for blip in run_el.findall(f".//{{{NS_A}}}blip"):
        rid = blip.get(f"{{{NS_R}}}embed")
        if rid and rid in p.part.related_parts:
            parte = p.part.related_parts[rid]
            b64 = base64.b64encode(parte.blob).decode("ascii")
            ct = parte.content_type
            dimensoes = dimensoes_no_sei(doc, blip, parte.blob)
            tamanho = f'width="{dimensoes[0]}" height="{dimensoes[1]}" ' if dimensoes else ""
            partes.append(f'<img alt="" {tamanho}src="data:{ct};base64,{b64}" style="max-width:100%;" />')

    # Chamada de nota de rodapé: o número da nota, entre colchetes, como no ODT
    for chamada in run_el.findall(qn("w:footnoteReference")):
        numero = notas_de_rodape(doc)[0].get(chamada.get(qn("w:id")) or "")
        if numero:
            partes.append(f"[{numero}]")

    # run.text já traduz <w:br> e <w:cr> em "\n" e <w:tab> em "\t", preservando a ordem
    texto = run.text or ""
    if texto:
        t = esc(texto).replace("\n", "<br />")
        rPr = run_el.find(qn("w:rPr"))
        # Lê o valor efetivo, com a herança dos estilos: <w:strike w:val="0"/> desliga o
        # riscado (o Word grava assim ao desmarcar), e um estilo riscado risca o run
        if estilos_do_paragrafo is None:
            estilos_do_paragrafo = _estilos_do_paragrafo(p)
        fontes = _fontes_do_run(run, estilos_do_paragrafo)
        b = _primeiro_definido(fontes, lambda f: f.bold)
        i = _primeiro_definido(fontes, lambda f: f.italic)
        u = _primeiro_definido(fontes, lambda f: f.underline)
        strike = bool(_primeiro_definido(fontes, lambda f: f.strike))
        cor = None
        if rPr is not None:
            c = rPr.find(qn("w:color"))
            if c is not None:
                val = c.get(qn("w:val"))
                if val and val.lower() not in ("auto", "000000"):
                    cor = val
        vert = rPr.find(qn("w:vertAlign")) if rPr is not None else None
        if vert is not None:
            va = vert.get(qn("w:val"))
            if va == "superscript":
                t = f"<sup>{t}</sup>"
            elif va == "subscript":
                t = f"<sub>{t}</sub>"
        if strike:
            t = f"<s>{t}</s>"
        if u:
            t = f"<u>{t}</u>"
        if i:
            t = f"<em>{t}</em>"
        if b:
            t = f"<strong>{t}</strong>"
        if cor:
            t = f'<span style="color:#{cor}">{t}</span>'
        partes.append(t)
    return "".join(partes)


def paragrafo_inline(doc: DocumentoWord, p: Paragraph) -> str:
    """Conteúdo inline completo do parágrafo (runs + hyperlinks, em ordem)."""
    # A cadeia de estilos do parágrafo é a mesma para todos os runs: calculada uma vez
    estilos = _estilos_do_paragrafo(p)
    out = []
    for child in _elementos_visiveis(p._p):
        if child.tag == qn("w:r"):
            out.append(run_para_html(doc, child, p, estilos))
        elif child.tag == qn("w:hyperlink"):
            rid = child.get(f"{{{NS_R}}}id")
            href = None
            if rid:
                try:
                    href = endereco_seguro(p.part.rels[rid].target_ref)
                except Exception:
                    href = None
            inner = "".join(run_para_html(doc, r, p, estilos) for r in child.findall(qn("w:r")))
            if href:
                out.append(f'<a href="{htmlmod.escape(href)}">{inner}</a>')
            else:
                out.append(inner)
    return "".join(out)


def _linha_curta_sem_classe(doc: DocumentoWord, p: Paragraph) -> str | None:
    """O texto do parágrafo, se ele pode ser linha do bloco de assinatura em qualquer
    alinhamento: curto, sem estilo com nome de classe e fora de título, lista e numeração
    digitada. Esses têm classe própria, que continua valendo no fim do texto.
    """
    texto = texto_visivel(p).strip()
    if not linha_curta(texto):
        return None
    nome_estilo = nome_do_estilo(p)
    if classe_sei_pelo_nome(nome_estilo) or re.search(r"(heading|t[ií]tulo)\s*\d", (nome_estilo or "").lower()):
        return None
    if item_digitado(p, texto) or formato_lista_xml(doc, p)[0] is not None:
        return None
    return texto


def _linha_de_assinatura(doc: DocumentoWord, p: Paragraph) -> bool:
    """Indica se o parágrafo pode ser linha do bloco de assinatura pela centralização."""
    texto = _linha_curta_sem_classe(doc, p)
    return texto is not None and pode_ser_linha_de_assinatura(texto, alinhamento(p))


def bloco_de_assinatura(doc: DocumentoWord) -> set:
    """Parágrafos do bloco de assinatura: os centralizados que fecham o documento.

    Parágrafos vazios não contam, e uma tabela interrompe o bloco. A política (quantas
    linhas, documento todo centralizado) fica em formatacao.linhas_de_assinatura, comum
    ao ODT.
    """
    elementos: list = []
    candidatas: list[bool] = []
    curtas: list[str | None] = []
    for filho in _blocos_visiveis(doc.element.body):
        if filho.tag == qn("w:tbl"):
            elementos.append(filho)
            candidatas.append(False)
            curtas.append(None)
        elif filho.tag == qn("w:p"):
            p = Paragraph(filho, doc)
            if texto_visivel(p).strip():
                elementos.append(filho)
                candidatas.append(_linha_de_assinatura(doc, p))
                curtas.append(_linha_curta_sem_classe(doc, p))
    return {elementos[i] for i in indices_de_assinatura(candidatas, curtas)}


def citacao_entre_aspas(doc: DocumentoWord) -> set:
    """Parágrafos que estão numa citação entre aspas com mais de uma linha.

    Achados antes da conversão, porque a citação pode abrir num parágrafo e fechar
    vários depois. Parágrafos vazios não contam, e uma tabela interrompe a citação. A
    política fica em formatacao.paragrafos_entre_aspas, comum ao ODT.
    """
    elementos: list = []
    textos: list[str | None] = []
    for filho in _blocos_visiveis(doc.element.body):
        if filho.tag == qn("w:tbl"):
            elementos.append(filho)
            textos.append(None)
        elif filho.tag == qn("w:p"):
            texto = texto_visivel(Paragraph(filho, doc))
            if texto.strip():
                elementos.append(filho)
                textos.append(texto)
    return {elementos[i] for i in paragrafos_entre_aspas(textos)}


# A marca da assinatura (RE_MARCA_ASSINATURA) sai sempre no mesmo texto, em itálico, e
# separa uma assinatura da outra
MARCA_ASSINATURA = "<em>[Assinado eletronicamente]</em>"
ABRE_ASSINATURA = f'<p class="{CLASSE_ASSINATURA}">'
# Linha em branco entre duas assinaturas. O &nbsp; impede o editor do SEI de descartar o
# parágrafo vazio
SEPARADOR_ASSINATURAS = f"{ABRE_ASSINATURA}&nbsp;</p>"


def ajustar_assinaturas(blocos: list[str]) -> list[str]:
    """Padroniza a marca de assinatura e separa as assinaturas com uma linha em branco.

    Olha as linhas com a classe da assinatura, em cada sequência delas: o documento pode
    ter assinaturas no meio (a do coordenador antes do "De acordo." da diretora), e não
    só no fim. Trabalha sobre o HTML, e não sobre o Word, porque o ODT e o Markdown chegam
    aqui com a classe já decidida (pelo nome do estilo no DOCX intermediário). A linha em
    branco só entra entre duas marcas da mesma sequência; sem marca não há separação, pois
    não dá para saber onde uma assinatura termina e a outra começa.
    """
    saida: list[str] = []
    marcas = 0
    for bloco in blocos:
        if not bloco.startswith(ABRE_ASSINATURA):
            marcas = 0
            saida.append(bloco)
            continue
        visivel = htmlmod.unescape(re.sub(r"<[^>]+>", "", bloco)).strip()
        if RE_MARCA_ASSINATURA.match(visivel):
            if marcas and saida[-1] != SEPARADOR_ASSINATURAS:
                saida.append(SEPARADOR_ASSINATURAS)
            marcas += 1
            bloco = f"{ABRE_ASSINATURA}{MARCA_ASSINATURA}</p>"
        saida.append(bloco)
    return saida


def _maiusculas_no_html(inline: str) -> str:
    """Caixa alta só no texto, fora das tags e das entidades (&amp; não pode virar &AMP;)."""
    return re.sub(r"(<[^>]+>|&[#\w]+;)|([^<&]+)", lambda m: m.group(1) or m.group(2).upper(), inline)


def converter_paragrafo(
    doc: DocumentoWord,
    p: Paragraph,
    dentro_tabela: bool = False,
    primeira_linha: bool = False,
    max_nivel: int = MAX_NIVEL_PADRAO,
    nivel_base_lista: int = 2,
    convencao: str = "titulos",
    citacao: CitacaoPorRecuo | None = None,
    assinatura: bool = False,
    entre_aspas: bool = False,
) -> tuple[str, str] | None:
    inline_bruto = paragrafo_inline(doc, p)
    inline = inline_bruto.strip()
    if not inline:
        return None

    # Estilo com o nome de uma classe do SEI é pedido explícito e vence qualquer heurística.
    # Em tabela, só as classes de tabela: uma célula com estilo "Texto_Justificado" (comum
    # em modelo que nomeia os estilos como o SEI) sairia com margem e fonte de corpo.
    explicita = classe_sei_pelo_nome(nome_do_estilo(p))
    if dentro_tabela and explicita and not explicita.startswith("Tabela_"):
        explicita = None

    # Item numerado digitado (1., 1.1., 3.1 ...) tem prioridade: vira Item_NivelN e o
    # SEI renumera sozinho. Fora de tabela apenas.
    texto = texto_visivel(p)
    prof = 0 if dentro_tabela or explicita else item_digitado(p, texto)
    if explicita:
        # Como os títulos do Word, o nível pedido pelo estilo não passa pelo limite de
        # --max-nivel, que vale só para número digitado
        cls = explicita
    elif assinatura:
        cls = CLASSE_ASSINATURA
    elif entre_aspas and citacao is not None and citacao.classe(formatacao_do_paragrafo(p, alinhamento(p)), texto, True):
        # Dentro da citação, "a)" e "1." são texto citado: nem alínea, nem item, e o
        # número fica no texto
        cls = "Citação"
        prof = 0
    elif prof:
        if convencao == "paragrafos":
            # Documento de parágrafos numerados: sem caixa alta nem tarja cinza
            cls = f"Paragrafo_Numerado_Nivel{prof}" if prof <= 3 else "Item_Alinea_Letra"
        else:
            # Acima do nível máximo, vira alínea (a, b, c). O SEI só tem Item_Nivel1 a 4: um
            # limite maior geraria Item_Nivel5, classe que o editor não conhece
            limite = max(1, min(max_nivel, MAX_NIVEL_PADRAO))
            cls = f"Item_Nivel{prof}" if prof <= limite else "Item_Alinea_Letra"
    else:
        cls = classe_do_paragrafo(
            doc,
            p,
            dentro_tabela,
            primeira_linha,
            nivel_base_lista=nivel_base_lista,
            convencao=convencao,
            # Na citação entre aspas, as regras de citação já foram vistas acima
            citacao=None if entre_aspas else citacao,
        )

    literal = cls == "Texto_Mono_Espaçado"
    if literal:
        # Em texto de largura fixa a indentação da primeira linha é conteúdo
        inline = inline_bruto.rstrip()
    elif re.fullmatch(r"[-–—]{3,}", texto.strip()):
        # Descarta separadores Markdown remanescentes (---, — —), exceto em bloco de código
        return None

    if cls == "__BULLET__":
        return (f"bullet{nivel_do_marcador(doc, p)}", f'<li class="{CLASSE_ITEM_LISTA}">{_md_links(inline)}</li>')

    # Remove numeração manual digitada para classes que possuem contadores automáticos
    if prof or cls.startswith("Item_Nivel"):
        inline = remover_tags_vazias(RE_STRIP_ITEM.sub(r"\1\2", inline, count=1))
    elif cls.startswith("Paragrafo_Numerado"):
        inline = RE_NUM_DECIMAL.sub("", inline, count=1)
    elif cls == "Item_Inciso_Romano":
        inline = RE_NUM_ROMANO.sub("", inline, count=1)
    elif cls == "Item_Alinea_Letra":
        inline = RE_NUM_LETRA.sub("", inline, count=1)

    if cls == "Tachado":
        # A classe já risca o parágrafo; o <s> em cada trecho seria redundante (e o
        # caminho de ODT e Markdown já sai sem ele)
        inline = re.sub(r"</?s>", "", inline)
    if not literal:
        # Em bloco de código, "[texto](url)" é conteúdo, e não link
        inline = _md_links(inline)
    if not inline.strip():
        return None

    if primeira_linha and dentro_tabela and "<strong>" not in inline:
        inline = f"<strong>{inline}</strong>"
    if assinatura:
        # Texto_Centralizado_Maiusculas_Negrito aplicava negrito e caixa alta pela classe;
        # a classe da assinatura não aplica, então o nome os leva no próprio texto
        formatacao = formatacao_do_paragrafo(p, "center")
        if formatacao.maiusculas and not texto_em_maiusculas(texto):
            inline = _maiusculas_no_html(inline)
        if formatacao.negrito and "<strong>" not in inline:
            inline = f"<strong>{inline}</strong>"
    return ("p", f'<p class="{cls}">{inline}</p>')


def larguras_percentuais(tbl: Table) -> list[float]:
    """Larguras das colunas da grade em %, a partir do tblGrid (twips)."""
    try:
        explicitas = tbl._tbl.tblPr.get("{urn:conversorsei}larguras")
        if explicitas:
            return [float(c) for c in explicitas.split(",")]
        cols = tbl._tbl.tblGrid.findall(qn("w:gridCol"))
        ws = [int(c.get(qn("w:w")) or 0) for c in cols]
        total = sum(ws) or 1
        pct = [round(100 * w / total, 1) for w in ws]
        if pct:
            pct[-1] = round(100 - sum(pct[:-1]), 1)
        return pct
    except Exception:
        return []


# Largura da área de texto do SEI em caracteres de tabela, para o cálculo pelo conteúdo:
# cerca de 800 px de largura, a uns 7 px por caractere em Calibri de 11 pt
CARACTERES_NA_LARGURA_DA_TABELA = 110
# Espaço da borda e do recuo da célula, contado como caracteres em cada coluna
FOLGA_DA_CELULA = 2
LARGURA_MINIMA_DA_COLUNA_PCT = 5.0


def colunas_iguais(pct: list[float]) -> bool:
    """Diz se as colunas têm todas a mesma largura, o padrão que ninguém escolheu.

    É assim que o Word insere uma tabela, e é assim que sai a tabela montada do Markdown,
    do ODT, do HTML e do PDF, que não trazem largura de coluna. Copiada como está, uma
    coluna só com os números 1, 2, 3 ocupava um terço da tabela. Larguras diferentes foram
    ajustadas por quem escreveu, e ficam.
    """
    return len(pct) > 1 and max(pct) - min(pct) <= 1


def larguras_pelo_conteudo(linhas: list[list[dict[str, Any]]], colunas: int) -> list[float]:
    """Largura de cada coluna em %, calculada pelo texto das células, como faz o navegador.

    Cada coluna tem um mínimo (a maior palavra, para não partir palavra) e um desejado (a
    maior linha de texto de uma célula). Se os desejados cabem na largura, a tabela se
    divide na proporção deles; se não cabem, cada coluna recebe o mínimo e o que sobra vai
    para as colunas de texto longo, na proporção do que lhes falta. Célula que ocupa várias
    colunas não entra na medida. Nenhuma coluna fica abaixo de 5%.
    """
    minimo = [1] * colunas
    desejado = [1] * colunas
    for linha in linhas:
        for cel in linha:
            if cel["colspan"] != 1 or cel["gridcol"] >= colunas:
                continue
            texto = re.sub(r"<br\s*/?>|</p>", "\n", cel["html"])
            texto = htmlmod.unescape(re.sub(r"<[^>]+>", "", texto)).replace("\xa0", " ")
            linhas_do_texto = [t.strip() for t in texto.split("\n") if t.strip()]
            palavras = [len(w) for t in linhas_do_texto for w in t.split()]
            c = cel["gridcol"]
            minimo[c] = max(minimo[c], *palavras, 1)
            desejado[c] = max(desejado[c], *(len(t) for t in linhas_do_texto), 1)
    minimo = [m + FOLGA_DA_CELULA for m in minimo]
    desejado = [d + FOLGA_DA_CELULA for d in desejado]

    capacidade = CARACTERES_NA_LARGURA_DA_TABELA
    if sum(desejado) <= capacidade or sum(minimo) >= capacidade:
        base = [float(d) if sum(desejado) <= capacidade else float(m) for d, m in zip(desejado, minimo, strict=True)]
    else:
        falta = [d - m for d, m in zip(desejado, minimo, strict=True)]
        sobra = capacidade - sum(minimo)
        base = [m + sobra * f / sum(falta) for m, f in zip(minimo, falta, strict=True)]

    pct = [100 * b / sum(base) for b in base]
    # O piso tira largura das colunas maiores, na proporção delas
    estreitas = [p < LARGURA_MINIMA_DA_COLUNA_PCT for p in pct]
    if any(estreitas) and not all(estreitas):
        resto = 100 - LARGURA_MINIMA_DA_COLUNA_PCT * sum(estreitas)
        largas = sum(p for p, e in zip(pct, estreitas, strict=True) if not e)
        pct = [LARGURA_MINIMA_DA_COLUNA_PCT if e else p * resto / largas for p, e in zip(pct, estreitas, strict=True)]
    pct = [round(p, 1) for p in pct]
    pct[-1] = round(100 - sum(pct[:-1]), 1)
    return pct


def celula_para_html(doc: DocumentoWord, tc, r: int, tbl: Table, max_nivel: int = MAX_NIVEL_PADRAO) -> str:
    """Conteúdo de uma célula: parágrafos e tabelas aninhadas."""
    out = []
    for child in _blocos_visiveis(tc):
        if child.tag == qn("w:p"):
            res = converter_paragrafo(
                doc, Paragraph(child, tbl), dentro_tabela=True, primeira_linha=(r == 0), max_nivel=max_nivel
            )
            if res:
                out.append(res[1])
        elif child.tag == qn("w:tbl"):
            # Aninhada, a tabela se mede pela célula, e não pela página
            out.append(converter_tabela(doc, Table(child, tbl), max_nivel=max_nivel, aninhada=True))
    if not out:
        out.append('<p class="Tabela_Texto_Centralizado">&nbsp;</p>')
    return "\n".join(out)


# Toda tabela sai centralizada, qualquer que seja o alinhamento no documento de origem,
# e com a proporção que tem no Word (largura_da_tabela). As larguras vão como atributo
# (width="80%"), e não no style: o Safari reescreve o HTML que uma página copia e troca a
# largura do style pelo valor medido numa página invisível (width:100% virava 718px
# fixos, e a tabela saía estreita e à esquerda no SEI). O atributo passa intacto. A
# tabela também fica sem style: testado no SEI, só o align centraliza depois da colagem,
# e margens automáticas no style chegam a anular o align.
def abertura_tabela(largura: int) -> str:
    return f'<table align="center" border="1" cellpadding="1" cellspacing="1" width="{largura}%">\n'


def _area_de_texto(doc: DocumentoWord) -> int | None:
    """Largura da área de texto da última seção, em twips, calculada uma vez por documento.

    doc.sections percorre o corpo inteiro atrás das seções: repetido a cada tabela, pesava
    num documento longo com muitas tabelas.
    """
    cache = _CACHE_ESTILOS.setdefault(doc.part, {})
    if "area_de_texto" not in cache:
        secao = doc.sections[-1]
        pagina, esquerda, direita = secao.page_width, secao.left_margin, secao.right_margin
        cache["area_de_texto"] = (
            None if pagina is None or esquerda is None or direita is None
            else pagina.twips - esquerda.twips - direita.twips
        )
    return cache["area_de_texto"]


def largura_da_tabela(doc: DocumentoWord, tbl: Table) -> int:
    """Largura da tabela em % da área de texto da página, como está no Word.

    Vem do tblW quando ele traz medida (dxa em twips, ou pct em cinquentésimos de ponto
    percentual) e, na falta dele (tipo auto), da soma das colunas da grade, que é como o
    Word desenha. Tabela do Markdown, do ODT e do PDF é montada com a grade na largura da
    página e sai com 100%. A área de texto é a da última seção: documento de trabalho quase
    nunca muda margem no meio. Sem medida confiável, ocupa a página inteira.
    """
    try:
        area = _area_de_texto(doc)
        if area is None:
            return 100
        tblW = tbl._tbl.tblPr.find(qn("w:tblW"))
        tipo = tblW.get(qn("w:type")) if tblW is not None else None
        valor = (tblW.get(qn("w:w")) or "") if tblW is not None else ""
        if tipo == "pct":
            pct = float(valor[:-1]) if valor.endswith("%") else int(valor) / 50
        elif tipo == "dxa" and int(valor) > 0:
            pct = 100 * int(valor) / area
        else:
            grade = sum(int(c.get(qn("w:w")) or 0) for c in tbl._tbl.tblGrid.findall(qn("w:gridCol")))
            pct = 100 * grade / area if grade else 100
    except Exception:
        return 100
    return max(10, min(100, round(pct)))


def converter_tabela(
    doc: DocumentoWord, tbl: Table, max_nivel: int = MAX_NIVEL_PADRAO, aninhada: bool = False
) -> str:
    """Converte tabela DOCX no padrão institucional do SEI."""
    pct = larguras_percentuais(tbl)
    linhas_html = []
    emitidas: dict = {}

    trs = list(_filhos_visiveis(tbl._tbl, (qn("w:tr"),)))
    for r, tr in enumerate(trs):
        gc = 0
        linha = []
        for tc in _filhos_visiveis(tr, (qn("w:tc"),)):
            tcPr = tc.find(qn("w:tcPr"))
            span = 1
            vmerge = None
            if tcPr is not None:
                gs = tcPr.find(qn("w:gridSpan"))
                if gs is not None:
                    span = int(gs.get(qn("w:val")) or 1)
                vm = tcPr.find(qn("w:vMerge"))
                if vm is not None:
                    vmerge = vm.get(qn("w:val")) or "continue"
            if vmerge == "continue":
                if gc in emitidas:
                    emitidas[gc]["rowspan"] += 1
                gc += span
                continue
            cel: dict[str, Any] = {
                "row": r,
                "gridcol": gc,
                "colspan": span,
                "rowspan": 1,
                "html": celula_para_html(doc, tc, r, tbl, max_nivel=max_nivel),
                "header": (r == 0),
            }
            emitidas[gc] = cel
            linha.append(cel)
            gc += span
        if linha:
            linhas_html.append(linha)

    if colunas_iguais(pct) and not tbl._tbl.tblPr.get("{urn:conversorsei}larguras"):
        pct = larguras_pelo_conteudo(linhas_html, len(pct))
    # A largura vai só na primeira linha, que fixa as colunas da tabela inteira
    for cel in (c for linha in linhas_html for c in linha if c["row"] == 0):
        if pct:
            cel["width"] = round(sum(pct[cel["gridcol"] : cel["gridcol"] + cel["colspan"]]), 1)

    linhas_td_html = []
    for linha in linhas_html:
        tds = []
        for cel in linha:
            attrs = []
            style = "vertical-align:middle;"
            # Largura como atributo pelo mesmo motivo da tabela (ver abertura_tabela)
            if cel.get("width"):
                attrs.append(f'width="{cel["width"]}%"')
            if cel["header"]:
                style += " background-color:#e6e6e6;"
            if cel["colspan"] > 1:
                attrs.append(f'colspan="{cel["colspan"]}"')
            if cel["rowspan"] > 1:
                attrs.append(f'rowspan="{cel["rowspan"]}"')
            attrs.append(f'style="{style.strip()}"')
            tds.append(f'      <td {" ".join(attrs)}>\n{cel["html"]}\n      </td>')
        linhas_td_html.append("    <tr>\n" + "\n".join(tds) + "\n    </tr>")

    largura = 100 if aninhada else largura_da_tabela(doc, tbl)
    return abertura_tabela(largura) + "  <tbody>\n" + "\n".join(linhas_td_html) + "\n  </tbody>\n</table>"


def abre_numeracao_nivel1(doc: DocumentoWord, p: Paragraph) -> bool:
    """Indica se o parágrafo abre numeração de nível 1, digitada ou automática.

    O número posto pela numeração automática do Word não aparece em p.text, então
    quem só olha o texto não vê os parágrafos numerados pela barra de ferramentas.
    Parágrafo com estilo de classe do SEI não conta: a classe dele já está decidida, e
    um "1." no texto não o torna item.
    """
    if classe_sei_pelo_nome(nome_do_estilo(p)):
        return False
    if item_digitado(p, texto_visivel(p)) == 1:
        return True
    fmt, ilvl = formato_lista_xml(doc, p)
    return fmt not in (None, "bullet", "lowerLetter", "upperRoman", "lowerRoman") and (ilvl or 0) == 0


def convencao_de_numeracao(doc: DocumentoWord) -> str:
    """Descobre se a numeração do documento marca títulos ou parágrafos.

    Retorna "paragrafos" quando a maioria dos itens de nível 1 é texto corrido
    (caso dos despachos, cujos parágrafos são numerados) e "titulos" caso contrário
    (caso das notas técnicas, com seções "1. ASSUNTO", "2. ANÁLISE").
    """
    corridos = titulos = 0
    for child in _blocos_visiveis(doc.element.body):
        if child.tag != qn("w:p"):
            continue
        p = Paragraph(child, doc)
        if not abre_numeracao_nivel1(doc, p):
            continue
        nome_estilo = (nome_do_estilo(p) or "").lower()
        if re.search(r"(heading|t[ií]tulo)\s*\d", nome_estilo):
            # Título do Word não depende de heurística: já é título
            continue
        if parece_texto_corrido(texto_visivel(p).strip()):
            corridos += 1
        else:
            titulos += 1
    return "paragrafos" if corridos > titulos else "titulos"


def documento_tem_item_nivel1(doc: DocumentoWord, convencao: str = "titulos") -> bool:
    """Indica se o corpo já traz um Item_Nivel1 vindo de título do Word ou de número digitado.

    Quando não há nenhum, as listas numeradas do Word passam a abrir em Item_Nivel1,
    para o documento não começar a numeração em "0.1".
    """
    for child in _blocos_visiveis(doc.element.body):
        if child.tag != qn("w:p"):
            continue
        p = Paragraph(child, doc)
        explicita = classe_sei_pelo_nome(nome_do_estilo(p))
        if explicita:
            if explicita == "Item_Nivel1":
                return True
            continue
        if convencao == "titulos" and item_digitado(p, texto_visivel(p)) == 1:
            return True
        nome_estilo = (nome_do_estilo(p) or "").lower()
        m = re.search(r"(heading|t[ií]tulo)\s*(\d)", nome_estilo)
        if m and int(m.group(2)) == 1:
            return True
    return False


def renderizar_lista(itens: list[tuple[int, str]]) -> str:
    """Preserva o recuo dos subitens sem quebrar a lista em blocos separados."""
    if not itens:
        return ""
    nivel_inicial = itens[0][0]
    abertura = f'<ul style="margin-left:{nivel_inicial * 2}em">' if nivel_inicial else "<ul>"
    partes = [abertura, itens[0][1][:-5]]
    anterior = 0
    for nivel, html in itens[1:]:
        relativo = max(0, min(nivel - nivel_inicial, anterior + 1))
        if relativo > anterior:
            partes.append("<ul>")
        else:
            partes.append("</li>")
            for _ in range(anterior - relativo):
                partes.append("</ul></li>")
        partes.append(html[:-5])
        anterior = relativo
    partes.append("</li>")
    for _ in range(anterior):
        partes.append("</ul></li>")
    partes.append("</ul>")
    return "".join(partes)


def converter_docx_para_blocos(
    caminho_docx: FonteDocumento,
    max_nivel: int = MAX_NIVEL_PADRAO,
    citacao: CitacaoPorRecuo | None = None,
    avisos: list[str] | None = None,
) -> list[str]:
    """Converte o .docx numa lista de blocos top-level (<p>, <table> ou <ul> inteiros).

    Aceita caminho, bytes ou stream binário. O conteúdo em memória deixa os pipelines de
    Markdown, PDF e da interface web entregarem o documento sem arquivo temporário.
    Com `citacao`, conta (e, se pedido, converte) os parágrafos com forma de citação.
    """
    with abrir_binario(caminho_docx, "documento.docx") as binario:
        doc = Document(binario)
    if avisos is not None:
        if notas_de_rodape(doc)[1]:
            avisos.append(AVISO_NOTAS)
        if any(True for _ in doc.element.body.iter(qn("w:endnoteReference"))):
            avisos.append("O documento tem notas de fim que não foram incorporadas. Confira o original antes de colar.")
        if any(True for _ in doc.element.body.iter(qn("w:txbxContent"))):
            avisos.append("O documento tem caixa de texto que pode não aparecer no HTML. Confira o original antes de colar.")
    blocos: list[str] = []
    lista: list[tuple[int, str]] | None = None
    # Decidido uma vez para o documento inteiro, para que itens irmãos de uma
    # mesma lista fiquem sempre no mesmo nível.
    convencao = convencao_de_numeracao(doc)
    nivel_base_lista = 2 if documento_tem_item_nivel1(doc, convencao) else 1
    if citacao is not None:
        citacao.fonte_do_corpo = fonte_do_corpo(doc)
    assinatura = bloco_de_assinatura(doc)
    aspas = citacao_entre_aspas(doc) if citacao is not None else set()

    for child in _blocos_visiveis(doc.element.body):
        if child.tag == qn("w:p"):
            res = converter_paragrafo(
                doc,
                Paragraph(child, doc),
                max_nivel=max_nivel,
                nivel_base_lista=nivel_base_lista,
                convencao=convencao,
                citacao=citacao,
                assinatura=child in assinatura,
                entre_aspas=child in aspas,
            )
            if res is None:
                continue
            tipo, htm = res
            if tipo.startswith("bullet"):
                if lista is None:
                    lista = []
                lista.append((int(tipo[6:]), htm))
            else:
                if lista is not None:
                    blocos.append(renderizar_lista(lista))
                    lista = None
                blocos.append(htm)
        elif child.tag == qn("w:tbl"):
            if lista is not None:
                blocos.append(renderizar_lista(lista))
                lista = None
            blocos.append(converter_tabela(doc, Table(child, doc), max_nivel=max_nivel))

    if lista is not None:
        blocos.append(renderizar_lista(lista))

    return ajustar_assinaturas(blocos) + blocos_das_notas(doc)


def converter_docx_para_html(
    caminho_docx: FonteDocumento, max_nivel: int = MAX_NIVEL_PADRAO
) -> str:
    """Converte o DOCX e retorna o HTML do corpo consolidado."""
    blocos = converter_docx_para_blocos(caminho_docx, max_nivel=max_nivel)
    return "\n".join(blocos)
