"""
html_converter.py — Converte páginas HTML (.html, .htm) para blocos HTML SEI.

A leitura usa só a biblioteca padrão (html.parser), sem dependência nova, e devolve
Markdown para o pipeline já existente, como o leitor de ODT. Nada do HTML de origem
chega à saída: só o texto e a formatação atravessam o DOCX intermediário, e script,
estilo e atributos de evento ficam para trás por construção.

Os casos pensados são o documento do próprio SEI (com as classes do editor, que valem
como nome de estilo), a saída deste conversor e o HTML simples de páginas e sistemas.
O HTML salvo pelo Word e o exportado pelo Google Docs guardam a formatação em estilos
da página e em comentários condicionais, que não são lidos: para eles, o .docx do
mesmo documento dá resultado melhor, e o aviso diz isso.
"""
from __future__ import annotations

import codecs
import html as htmlmod
import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser

from conversorsei.entrada import FonteDocumento, ler_bytes, nome_da_fonte
from conversorsei.formatacao import (
    ESTILO_NUMERO_LITERAL,
    CitacaoPorRecuo,
    Formatacao,
    classe_sei_pelo_nome,
    linha_curta,
    linhas_de_assinatura,
    pode_ser_linha_de_assinatura,
)
from conversorsei.md_converter import (
    MARCA_QUEBRA_ODT,
    comeca_com_item,
    converter_texto_md_para_blocos,
    decodificar_texto,
    desescapar_markdown,
    escapar_markdown,
    linha_com_classe,
    linha_de_assinatura,
    marcar_colunas_mescladas,
    riscar_inteiro,
)

EXTENSOES_HTML = frozenset({".html", ".htm"})

# Conteúdo que não é texto do documento. O <head> não entra na lista: sem o </head>,
# comum em HTML escrito à mão, o corpo inteiro seria ignorado. O que ele tem de texto
# (o título) já está aqui
IGNORADAS = frozenset(
    {"script", "style", "title", "noscript", "template", "svg", "math", "iframe", "object", "select", "textarea"}
)
VAZIAS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
TITULOS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}
LISTAS = frozenset({"ul", "ol", "dl"})
# Abrir um destes fecha o <p> aberto, como faz o navegador
FECHAM_P = frozenset(
    {
        "address", "article", "aside", "blockquote", "center", "details", "div", "dl", "fieldset", "figcaption",
        "figure", "footer", "form", "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul",
        *TITULOS,
    }
)
BLOCOS = FECHAM_P | {
    "body", "caption", "dd", "dt", "head", "html", "li", "summary", "tbody", "td", "tfoot", "th", "thead", "tr",
}
# Fechamentos implícitos: a etiqueta que abre, as que ela fecha e onde a busca para
FECHAMENTO_IMPLICITO: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "li": (frozenset({"li"}), frozenset({"ul", "ol", "table"})),
    "dt": (frozenset({"dt", "dd"}), frozenset({"dl", "table"})),
    "dd": (frozenset({"dt", "dd"}), frozenset({"dl", "table"})),
    "td": (frozenset({"td", "th"}), frozenset({"tr", "table"})),
    "th": (frozenset({"td", "th"}), frozenset({"tr", "table"})),
    "tr": (frozenset({"tr"}), frozenset({"table"})),
    "thead": (frozenset({"thead", "tbody", "tfoot"}), frozenset({"table"})),
    "tbody": (frozenset({"thead", "tbody", "tfoot"}), frozenset({"table"})),
    "tfoot": (frozenset({"thead", "tbody", "tfoot"}), frozenset({"table"})),
}
LIMITES_DO_P = frozenset({"td", "th", "li", "table", "blockquote", "div", "body", "caption", "dd"})

# Espaço do HTML, que o navegador junta num só. O espaço inseparável fica de fora
RE_ESPACOS = re.compile(r"[ \t\n\r\f]+")
RE_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
# Pela especificação do HTML, quem declara Latin-1 ou ASCII é lido como Windows-1252
CODIFICACAO_POR_APELIDO = {"iso-8859-1": "cp1252", "iso8859-1": "cp1252", "latin1": "cp1252", "us-ascii": "cp1252"}
ALINHAMENTOS = {
    "left": "left", "start": "left", "right": "right", "end": "right",
    "center": "center", "-webkit-center": "center", "justify": "justify",
}
PESOS_NUMERICOS = frozenset(str(peso) for peso in range(100, 1000, 100))
CLASSE_DE_CELULA_POR_ALINHAMENTO = {"center": "Tabela_Texto_Centralizado", "right": "Tabela_Texto_Alinhado_Direita"}

# Texto que o SEI acrescenta ao documento e gera de novo no documento novo: a assinatura
# eletrônica, a nota de autenticidade e a referência do rodapé
RE_TEXTO_DO_SEI = re.compile(
    r"^\s*(?:Documento assinado eletronicamente por"
    r"|A autenticidade d(?:o|este) documento pode ser conferida"
    r"|Refer[eê]ncia:\s*Processo\s+n[º°o]\s*[\d./-]+\s*SEI\s+n[º°o]\s*\d+\s*$)",
    re.IGNORECASE,
)
RE_HTML_DO_WORD = re.compile(
    r"urn:schemas-microsoft-com:office:word|<meta[^>]+content=[\"']?Microsoft Word", re.IGNORECASE
)
# O arquivo exportado, e não a cópia: na cópia (marca docs-internal-guid), a ênfase vem no
# style de cada trecho, que é lido
RE_HTML_DO_GOOGLE_DOCS = re.compile(r"<body[^>]+class=\"[^\"]*\bdoc-content\b", re.IGNORECASE)


@dataclass(eq=False)
class No:
    """Elemento do HTML, com os filhos na ordem: outros elementos e trechos de texto."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    filhos: list[No | str] = field(default_factory=list)


# Tipo de numeração de <ol> (o atributo type) pelo list-style-type do CSS
TIPO_POR_ESTILO_DE_LISTA = {
    "lower-alpha": "a",
    "lower-latin": "a",
    "upper-alpha": "A",
    "upper-latin": "A",
    "lower-roman": "i",
    "upper-roman": "I",
}
ROMANOS = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
           (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))  # fmt: skip


def numero_do_item(posicao: int, tipo: str) -> str:
    """O número de um item de <ol>, como se escreve no texto: "1.", "a)", "A)", "I -"."""
    if tipo in ("a", "A") and posicao > 0:
        letras = ""
        while posicao > 0:
            posicao, resto = divmod(posicao - 1, 26)
            letras = chr(ord("a") + resto) + letras
        return f"{letras.upper() if tipo == 'A' else letras})"
    if tipo in ("i", "I") and posicao > 0:
        romano = ""
        for valor, simbolo in ROMANOS:
            while posicao >= valor:
                romano += simbolo
                posicao -= valor
        return f"{romano if tipo == 'I' else romano.lower()} -"
    return f"{posicao}."


class MontadorDeArvore(HTMLParser):
    """Monta a árvore do documento, com os fechamentos que o navegador deduz.

    O HTML real deixa <p>, <li> e <td> sem fechar. Sem deduzir o fechamento, cada
    parágrafo ficaria dentro do anterior, e a lista inteira dentro do primeiro item.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = No("raiz")
        self.pilha: list[No] = [self.raiz]
        self.ignorando: str | None = None
        self.profundidade_ignorada = 0

    def _fechar_ate(self, alvos: frozenset[str], limites: frozenset[str]) -> None:
        for indice in range(len(self.pilha) - 1, 0, -1):
            tag = self.pilha[indice].tag
            if tag in alvos:
                del self.pilha[indice:]
                return
            if tag in limites:
                return

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.ignorando:
            self.profundidade_ignorada += tag == self.ignorando
            return
        if tag in IGNORADAS:
            self.ignorando, self.profundidade_ignorada = tag, 1
            return
        if tag in FECHAM_P:
            self._fechar_ate(frozenset({"p"}), LIMITES_DO_P)
        if tag in FECHAMENTO_IMPLICITO:
            self._fechar_ate(*FECHAMENTO_IMPLICITO[tag])
        no = No(tag, {nome.lower(): valor or "" for nome, valor in attrs})
        self.pilha[-1].filhos.append(no)
        if tag not in VAZIAS:
            self.pilha.append(no)

    def handle_endtag(self, tag: str) -> None:
        if self.ignorando:
            if tag == self.ignorando:
                self.profundidade_ignorada -= 1
                if not self.profundidade_ignorada:
                    self.ignorando = None
            return
        # Fechamento sem abertura correspondente (um </p> solto) não mexe na árvore
        for indice in range(len(self.pilha) - 1, 0, -1):
            if self.pilha[indice].tag == tag:
                del self.pilha[indice:]
                return

    def handle_data(self, data: str) -> None:
        if not self.ignorando:
            self.pilha[-1].filhos.append(data)


def montar_arvore(texto: str) -> No:
    montador = MontadorDeArvore()
    montador.feed(texto)
    montador.close()
    return montador.raiz


def decodificar_html(conteudo: bytes, avisos: list[str] | None = None) -> str:
    """Texto do HTML, pela codificação declarada no <meta charset>.

    O Word salva HTML em Windows-1252 e o declara. Sem declaração, ou com uma que não
    serve, vale a mesma leitura do .txt, que distingue UTF-8 de Windows-1252 pelos bytes.
    """
    bom = conteudo.startswith((codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
    declarada = None if bom else RE_CHARSET.search(conteudo[:4096])
    if declarada:
        nome = declarada.group(1).decode("ascii").lower()
        try:
            codificacao = codecs.lookup(CODIFICACAO_POR_APELIDO.get(nome, nome)).name
        except LookupError:
            codificacao = None
        # Declaração de UTF-16 num arquivo lido como ASCII é engano de quem gravou
        if codificacao and not codificacao.startswith("utf-16"):
            try:
                return conteudo.decode(codificacao)
            except UnicodeDecodeError:
                pass
    return decodificar_texto(conteudo, estendido=False, avisos=avisos)


def _estilo(no: No) -> dict[str, str]:
    """Propriedades do atributo style, com nome e valor em minúsculas."""
    propriedades = {}
    for declaracao in no.attrs.get("style", "").split(";"):
        nome, _, valor = declaracao.partition(":")
        if valor.strip():
            propriedades[nome.strip().lower()] = valor.strip().lower()
    return propriedades


def alinhamento_do_no(no: No) -> str | None:
    valor = _estilo(no).get("text-align") or no.attrs.get("align", "").lower()
    if no.tag == "center":
        valor = "center"
    return ALINHAMENTOS.get(valor.replace("!important", "").strip())


def classe_do_no(no: No) -> str | None:
    """Primeira classe do SEI no atributo class, que vale como nome de estilo."""
    for nome in no.attrs.get("class", "").split():
        classe = classe_sei_pelo_nome(nome)
        if classe:
            return classe
    return None


def _tem_bloco(no: No) -> bool:
    return any(isinstance(filho, No) and filho.tag in BLOCOS for filho in no.filhos)


def _envolver(texto: str, abre: str, fecha: str | None = None) -> str:
    """Põe a marcação em volta do texto, deixando de fora os espaços das pontas.

    "** negrito **" não é negrito no Markdown, e o HTML costuma trazer o espaço
    dentro do <strong> e do <a>.
    """
    m = re.fullmatch(r"(\s*)(.*?)(\s*)", texto, re.DOTALL)
    if not m or not m.group(2):
        return texto
    return f"{m.group(1)}{abre}{m.group(2)}{abre if fecha is None else fecha}{m.group(3)}"


@dataclass(frozen=True)
class Enfase:
    negrito: bool = False
    italico: bool = False
    riscado: bool = False


def enfase_do_no(no: No, herdada: Enfase) -> Enfase:
    """Ênfase do elemento: a da etiqueta, corrigida pelo atributo style.

    O style vence a etiqueta porque o Google Docs embrulha o texto copiado num
    <b style="font-weight:normal">.
    """
    negrito = herdada.negrito or no.tag in ("b", "strong")
    italico = herdada.italico or no.tag in ("i", "em")
    riscado = herdada.riscado or no.tag in ("s", "strike", "del")
    estilo = _estilo(no)
    peso = estilo.get("font-weight", "")
    if peso in ("bold", "bolder") or (peso in PESOS_NUMERICOS and int(peso) >= 600):
        negrito = True
    elif peso in ("normal", "lighter") or peso in PESOS_NUMERICOS:
        negrito = False
    if estilo.get("font-style") in ("italic", "oblique"):
        italico = True
    elif estilo.get("font-style") == "normal":
        italico = False
    decoracao = estilo.get("text-decoration", "") + " " + estilo.get("text-decoration-line", "")
    if "line-through" in decoracao:
        riscado = True
    return Enfase(negrito, italico, riscado)


def _endereco_do_link(href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:")):
        return None
    # Parêntese e espaço encerrariam o endereço no Markdown
    return href.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


@dataclass
class Contexto:
    alinhamento: str | None = None
    citacao: bool = False


class LeitorHtml:
    """Percorre a árvore devolvendo linhas de Markdown, na forma do leitor de ODT."""

    def __init__(self) -> None:
        self.linhas: list[str] = []
        # (índice da linha, candidata, formato, texto, texto da linha curta) de cada
        # parágrafo ou tabela, para achar o bloco de assinatura, como no ODT
        self.registros: list[tuple[int, bool, Formatacao, str, str | None]] = []
        self.imagens = False
        self.mescladas_entre_linhas = False
        self.textos_do_sei = 0

    def _registrar(
        self, candidata: bool = False, formato: Formatacao | None = None, texto: str = "", curta: str | None = None
    ) -> None:
        self.registros.append((len(self.linhas) - 1, candidata, formato or Formatacao(), texto, curta))

    # Texto dos parágrafos

    def _inline(self, nos: list[No | str], enfase: Enfase, trechos: list[Enfase]) -> str:
        partes: list[str] = []
        for no in nos:
            if isinstance(no, str):
                texto = RE_ESPACOS.sub(" ", no)
                if texto.strip():
                    trechos.append(enfase)
                partes.append(escapar_markdown(texto))
                continue
            if no.tag == "br":
                partes.append(MARCA_QUEBRA_ODT)
                continue
            if no.tag == "img":
                self.imagens = True
                continue
            propria = enfase_do_no(no, enfase)
            interno = self._inline(no.filhos, propria, trechos)
            if no.tag == "a":
                endereco = _endereco_do_link(no.attrs.get("href", ""))
                if endereco:
                    interno = _envolver(interno, "[", f"]({endereco})")
            if propria.negrito and not enfase.negrito:
                interno = _envolver(interno, "**")
            if propria.italico and not enfase.italico:
                interno = _envolver(interno, "*")
            if propria.riscado and not enfase.riscado:
                interno = _envolver(interno, "~~")
            if no.tag in BLOCOS:
                # Parágrafos dentro de um item de lista ou de uma célula viram uma linha só
                interno = f" {interno} "
            partes.append(interno)
        return "".join(partes)

    def _texto(self, nos: list[No | str], trechos: list[Enfase]) -> str:
        texto = RE_ESPACOS.sub(" ", self._inline(nos, Enfase(), trechos))
        texto = re.sub(f" ?{MARCA_QUEBRA_ODT} ?", MARCA_QUEBRA_ODT, texto)
        return texto.strip().strip(MARCA_QUEBRA_ODT).strip()

    def _literal(self, no: No) -> str:
        """Texto de um bloco de código, com os espaços e as quebras do original."""
        partes = []
        for filho in no.filhos:
            if isinstance(filho, str):
                partes.append(filho)
            elif filho.tag == "br":
                partes.append("\n")
            else:
                partes.append(self._literal(filho))
        return "".join(partes)

    # Blocos

    def blocos(self, no: No, contexto: Contexto) -> None:
        """Converte os filhos de um contêiner. Texto solto entre blocos vira parágrafo."""
        soltos: list[No | str] = []
        for filho in no.filhos:
            if isinstance(filho, No) and filho.tag in BLOCOS:
                self._paragrafo(soltos, None, contexto)
                soltos = []
                self._bloco(filho, contexto)
            else:
                soltos.append(filho)
        self._paragrafo(soltos, None, contexto)

    def _bloco(self, no: No, contexto: Contexto) -> None:
        tag = no.tag
        contexto = replace(contexto, alinhamento=alinhamento_do_no(no) or contexto.alinhamento)
        if tag == "hr":
            return
        if tag in TITULOS and not classe_do_no(no):
            self._titulo(no, TITULOS[tag])
        elif tag in LISTAS:
            self._lista(no, 0)
            self.linhas.append("")
        elif tag == "table":
            self._tabela(no, contexto)
        elif tag == "blockquote":
            self.blocos(no, replace(contexto, citacao=True))
        elif tag == "pre" or classe_do_no(no) == "Texto_Mono_Espaçado":
            self._codigo(no)
        elif _tem_bloco(no):
            self.blocos(no, contexto)
        else:
            self._paragrafo(no.filhos, no, contexto)

    def _paragrafo(self, nos: list[No | str], dono: No | None, contexto: Contexto) -> None:
        trechos: list[Enfase] = []
        texto = self._texto(nos, trechos)
        if not texto:
            return
        visivel = desescapar_markdown(texto)
        if RE_TEXTO_DO_SEI.match(visivel):
            self.textos_do_sei += 1
            return
        formato = Formatacao(
            alinhamento=contexto.alinhamento,
            negrito=all(t.negrito for t in trechos),
            riscado=all(t.riscado for t in trechos),
        )
        if formato.riscado:
            texto = riscar_inteiro(texto)
        explicita = "Citação" if contexto.citacao else (classe_do_no(dono) if dono is not None else None)
        self.linhas.append(linha_com_classe(texto, formato, explicita))
        sem_classe = not explicita and not comeca_com_item(texto)
        candidata = sem_classe and pode_ser_linha_de_assinatura(visivel, formato.alinhamento)
        self._registrar(candidata, formato, texto, visivel if sem_classe and linha_curta(visivel) else None)
        self.linhas.append("")

    def _titulo(self, no: No, nivel: int) -> None:
        trechos: list[Enfase] = []
        texto = self._texto(no.filhos, trechos)
        if not texto:
            return
        if all(t.riscado for t in trechos):
            texto = riscar_inteiro(texto)
        self.linhas.append(f"{'#' * nivel} {texto}")
        self._registrar()
        self.linhas.append("")

    def _codigo(self, no: No) -> None:
        codigo = self._literal(no).replace("\r\n", "\n").strip("\n")
        if not codigo.strip():
            return
        self.linhas.extend(["```", *codigo.split("\n"), "```"])
        self._registrar()
        self.linhas.append("")

    def _lista(self, no: No, nivel: int) -> None:
        """Itens de lista com marcadores, na forma do leitor de ODT.

        Os itens saem colados, com dois espaços por nível: uma linha em branco entre
        eles quebraria a lista em várias no Markdown. A lista numerada vai para
        _lista_numerada.
        """
        if no.tag == "ol":
            self._lista_numerada(no, nivel)
            return
        for filho in no.filhos:
            if isinstance(filho, str):
                continue
            if filho.tag in LISTAS:
                self._lista(filho, nivel + 1)
                continue
            proprio = [f for f in filho.filhos if not (isinstance(f, No) and f.tag in LISTAS)]
            trechos: list[Enfase] = []
            texto = self._texto(proprio, trechos)
            if texto:
                if all(t.riscado for t in trechos):
                    texto = riscar_inteiro(texto)
                self.linhas.append(f"{'  ' * min(nivel, 3)}- {texto}")
                self._registrar()
            for sub in filho.filhos:
                if isinstance(sub, No) and sub.tag in LISTAS:
                    self._lista(sub, nivel + 1)

    def _lista_numerada(self, no: No, nivel: int) -> None:
        """Itens de <ol> como parágrafos com o número escrito no texto ("1.", "a)").

        O SEI não tem lista numerada: as classes numeradas entram na sequência dos itens
        do próprio documento, e o Item_Nivel1 sai em caixa alta com tarja cinza. A lista
        colada costuma ser texto citado (perguntas de um pedido, incisos de uma norma),
        e o número escrito nunca se mistura com a numeração do documento. O estilo
        ESTILO_NUMERO_LITERAL impede o docx_converter de ler o "1." como item digitado.
        """
        tipo = no.attrs.get("type") or TIPO_POR_ESTILO_DE_LISTA.get(_estilo(no).get("list-style-type", ""), "1")
        try:
            posicao = int(no.attrs.get("start") or 1)
        except ValueError:
            posicao = 1
        for filho in no.filhos:
            if isinstance(filho, str):
                continue
            if filho.tag in LISTAS:
                self._lista(filho, nivel + 1)
                continue
            try:
                posicao = int(filho.attrs.get("value") or posicao)
            except ValueError:
                pass
            proprio = [f for f in filho.filhos if not (isinstance(f, No) and f.tag in LISTAS)]
            trechos: list[Enfase] = []
            texto = self._texto(proprio, trechos)
            if texto:
                if all(t.riscado for t in trechos):
                    texto = riscar_inteiro(texto)
                texto = f"{numero_do_item(posicao, tipo)} {texto}"
                self.linhas.append(linha_com_classe(texto, Formatacao(), ESTILO_NUMERO_LITERAL))
                self._registrar()
                self.linhas.append("")
            posicao += 1
            for sub in filho.filhos:
                if isinstance(sub, No) and sub.tag in LISTAS:
                    self._lista(sub, nivel + 1)
                    self.linhas.append("")

    def _linhas_da_tabela(self, tabela: No) -> list[No]:
        linhas = []
        for filho in tabela.filhos:
            if isinstance(filho, No):
                if filho.tag == "tr":
                    linhas.append(filho)
                elif filho.tag in ("thead", "tbody", "tfoot"):
                    linhas.extend(f for f in filho.filhos if isinstance(f, No) and f.tag == "tr")
        return linhas

    def _celula(self, celula: No) -> str:
        texto = self._texto(celula.filhos, [])
        # A barra vertical é o separador da tabela Markdown e não pode vir do conteúdo
        texto = texto.replace("|", r"\|")
        paragrafo = next((f for f in celula.filhos if isinstance(f, No) and f.tag in ("p", "div")), None)
        classe = classe_do_no(paragrafo) if paragrafo is not None else None
        if not (classe or "").startswith("Tabela_"):
            alinhamento = alinhamento_do_no(paragrafo) if paragrafo is not None else None
            classe = CLASSE_DE_CELULA_POR_ALINHAMENTO.get(alinhamento or alinhamento_do_no(celula) or "")
        if texto and classe:
            # O <p> leva a classe pela tabela Markdown até o DOCX, como num parágrafo
            texto = f'<p class="{classe}">{htmlmod.escape(texto, quote=False)}</p>'
        try:
            colunas = int(celula.attrs.get("colspan") or 1)
            self.mescladas_entre_linhas |= int(celula.attrs.get("rowspan") or 1) > 1
        except ValueError:
            colunas = 1
        return marcar_colunas_mescladas(texto, max(colunas, 1))

    def _tabela(self, tabela: No, contexto: Contexto) -> None:
        linhas = self._linhas_da_tabela(tabela)
        celulas = [[c for c in linha.filhos if isinstance(c, No) and c.tag in ("td", "th")] for linha in linhas]
        celulas = [linha for linha in celulas if linha]
        if not celulas:
            return
        if len(celulas) == 1 and len(celulas[0]) == 1 and _tem_bloco(celulas[0][0]):
            # Tabela de uma célula com vários parágrafos é moldura de página: numa tabela
            # Markdown, o documento inteiro viraria uma linha só
            self.blocos(celulas[0][0], contexto)
            return
        if RE_TEXTO_DO_SEI.match(desescapar_markdown(self._texto(tabela.filhos, []))):
            # A assinatura do SEI é uma tabela com o selo e o texto
            self.textos_do_sei += 1
            return
        md = [[self._celula(c) for c in linha] for linha in celulas]
        if not any(texto for linha in md for texto in linha):
            return
        self.linhas.append("| " + " | ".join(md[0]) + " |")
        self.linhas.append("| " + " | ".join(["---"] * max(len(linha) for linha in md)) + " |")
        self.linhas.extend("| " + " | ".join(linha) + " |" for linha in md[1:])
        self._registrar()
        self.linhas.append("")

    def markdown(self, raiz: No) -> str:
        self.blocos(raiz, Contexto())
        n = linhas_de_assinatura(
            [candidata for _, candidata, _, _, _ in self.registros], [curta for *_, curta in self.registros]
        )
        for indice, _, formato, texto, _ in self.registros[len(self.registros) - n :] if n else []:
            self.linhas[indice] = linha_de_assinatura(texto, formato)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.linhas)).strip()


def extrair_markdown_html(fonte: FonteDocumento, avisos: list[str] | None = None, colado: bool = False) -> str:
    """Extrai o conteúdo de um .html como Markdown.

    `colado` indica o HTML da área de transferência, e não um arquivo salvo: ali, o
    Word e o Google Docs põem a formatação no próprio texto, e o aviso para converter o
    .docx não vale.
    """
    nome = nome_da_fonte(fonte, "documento.html")
    texto = decodificar_html(ler_bytes(fonte), avisos)
    leitor = LeitorHtml()
    markdown = leitor.markdown(montar_arvore(texto))
    if not markdown:
        if colado:
            raise RuntimeError("Nenhum texto foi encontrado no conteúdo colado.")
        raise RuntimeError(f"Nenhum texto foi encontrado em {nome}: a página pode estar vazia ou conter apenas imagens.")
    if avisos is not None:
        # Na área de transferência, o Word e o Google Docs trazem a formatação no texto
        if not colado and RE_HTML_DO_WORD.search(texto[:5000]):
            avisos.append(
                "Este HTML foi salvo pelo Word, que não guarda ali a numeração e os estilos do documento. "
                "Se tiver o original, converta o .docx."
            )
        elif not colado and RE_HTML_DO_GOOGLE_DOCS.search(texto[:20000]):
            avisos.append(
                "Este HTML veio do Google Docs, que marca negrito e itálico de um jeito que não foi lido. "
                "Para manter a formatação, baixe o documento como .docx (Arquivo, Fazer download, "
                "Microsoft Word) e converta esse arquivo."
            )
        if leitor.imagens:
            avisos.append("Imagens do HTML não foram incorporadas. Insira-as no SEI após conferir o original.")
        if leitor.mescladas_entre_linhas:
            avisos.append("Uma tabela tem células mescladas entre linhas. Confira a tabela no resultado e no SEI.")
        if leitor.textos_do_sei:
            avisos.append(
                "A assinatura eletrônica e a nota de autenticidade do SEI foram retiradas: "
                "o SEI as gera de novo no documento novo."
            )
    return markdown + "\n"


def converter_html_para_blocos(
    fonte: FonteDocumento,
    max_nivel: int = 4,
    avisos: list[str] | None = None,
    colado: bool = False,
    citacao: CitacaoPorRecuo | None = None,
) -> list[str]:
    """Converte um arquivo HTML para blocos HTML SEI.

    O Markdown vem com a semântica do .md, e não a do texto extraído de ODT e PDF: o
    <h1> sem número é o título do documento, como o "#" num .md.
    """
    markdown = extrair_markdown_html(fonte, avisos=avisos, colado=colado)
    return converter_texto_md_para_blocos(markdown, max_nivel=max_nivel, citacao=citacao)
