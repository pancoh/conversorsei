"""
formatacao.py — Escolhe a classe SEI de um parágrafo a partir da sua formatação.

As regras ficam aqui, e não em cada conversor, porque Word e ODT descrevem a mesma
coisa (caixa alta, riscado, fundo) com vocabulários diferentes. Cada leitor traduz o que
sabe para uma Formatacao e todos recebem a mesma resposta.

Só entram marcas que alguém põe de propósito: riscar o parágrafo inteiro, sombrear em
cinza, espaçar as letras, centralizar em caixa alta, diminuir a fonte da tabela. Regras
que tentam adivinhar a intenção por medida (ementa pelo recuo, código pela fonte)
erravam em documentos comuns (assinatura recuada, documento inteiro em Courier) e
ficaram de fora: essas classes vêm pelo nome do estilo ou pelo Markdown.

A citação pela forma é a exceção, e só vale a pedido (CitacaoPorRecuo). Documento
real quase nunca usa estilo: a citação costuma vir recuada e em fonte menor, ou como um
parágrafo inteiro entre aspas. A conversão conta esses parágrafos e deixa quem converte
decidir: a interface oferece a troca, em vez de a regra adivinhar sozinha.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from conversorsei.validador import obter_classes_validas_css

# Tabela_Texto_8 e Tabela_Texto_10 são as variantes em fonte menor das células
FONTE_MAXIMA_TABELA_8_PT = 8.0
FONTE_MAXIMA_TABELA_10_PT = 10.0
# Menos que isso ("I", "OK") não basta para dizer que o parágrafo está em caixa alta
MINIMO_LETRAS_MAIUSCULAS = 3
# A ABNT pede 4 cm para a citação longa. Metade disso já não acontece por acaso num
# parágrafo comum, e deixa folga para modelos com recuo menor
RECUO_MINIMO_CITACAO_CM = 2.0
# Perto do que cabe numa linha do SEI (Calibri 12 pt). Uma fala curta entre aspas fica no
# texto; a citação que passa de uma linha costuma ir em parágrafo próprio
MINIMO_LETRAS_CITACAO_ENTRE_ASPAS = 100
# Estilo interno do DOCX intermediário (não é classe do SEI): o parágrafo traz escrito o
# número de uma lista numerada, que o docx_converter não deve ler como item digitado
ESTILO_NUMERO_LITERAL = "Conversor_Numero_Literal"
# Aspas de abertura e a de fechamento que corresponde a cada uma
ASPAS = {'"': '"', "“": "”", "«": "»"}
# Depois das aspas, só pontuação e a referência entre parênteses: "..." (SILVA, 2020, p. 3).
RE_DEPOIS_DAS_ASPAS = re.compile(r"[\s.,;:]*(?:\([^()]*\)[\s.,;:]*)?")


@dataclass
class Formatacao:
    """O que se sabe da aparência de um parágrafo, no vocabulário comum aos leitores.

    Os campos booleanos valem para o texto inteiro: um parágrafo com uma só palavra em
    negrito não está "em negrito". Quem não consegue ler um atributo deixa o padrão,
    que nunca dispara regra.
    """

    alinhamento: str | None = None
    tamanho_pt: float | None = None
    negrito: bool = False
    maiusculas: bool = False
    riscado: bool = False
    fundo_cinza: bool = False
    letras_espacadas: bool = False
    recuo_esquerdo_cm: float = 0.0


def maior_tamanho(tamanhos: list[float | None]) -> float | None:
    """Maior tamanho de fonte do parágrafo, ou None se algum trecho não tiver tamanho conhecido.

    Melhor não aplicar a regra do que aplicá-la olhando só parte do texto.
    """
    if not tamanhos or any(t is None for t in tamanhos):
        return None
    return max(t for t in tamanhos if t is not None)


@lru_cache(maxsize=1)
def classes_sei() -> frozenset[str]:
    """Classes aceitas pelo SEI, lidas uma vez do CSS institucional."""
    return frozenset(obter_classes_validas_css())


def classe_sei_pelo_nome(nome_estilo: str | None) -> str | None:
    """Classe SEI cujo nome é o próprio nome do estilo do parágrafo.

    É o caminho explícito: um modelo do Word com estilos chamados como as classes do
    SEI, ou um <p class="..."> escrito no Markdown, que o conversor de Markdown grava no
    DOCX intermediário como nome de estilo. Aceita espaço no lugar do sublinhado porque
    alguns editores trocam um pelo outro ao exibir o nome.
    """
    nome = (nome_estilo or "").strip()
    if not nome:
        return None
    for candidato in (nome, nome.replace(" ", "_")):
        if candidato in classes_sei():
            return candidato
    return None


def texto_em_maiusculas(texto: str) -> bool:
    """Indica se todas as letras do texto estão em caixa alta.

    Considera só letras que têm as duas caixas: "Nº" e algarismos não contam contra.
    """
    letras = [c for c in texto if c.lower() != c.upper()]
    return len(letras) >= MINIMO_LETRAS_MAIUSCULAS and all(c == c.upper() for c in letras)


def classe_por_formatacao(f: Formatacao) -> str | None:
    """Classe SEI sugerida pela formatação, ou None quando nenhuma regra se aplica.

    O alinhamento comum (centralizado, à direita) fica para quem chama, como sempre ficou.
    """
    if f.riscado:
        return "Tachado"
    if f.fundo_cinza and f.negrito:
        return "Texto_Fundo_Cinza_Maiusculas_Negrito" if f.maiusculas else "Texto_Fundo_Cinza_Negrito"
    if f.letras_espacadas and f.negrito:
        return "Texto_Espaco_Duplo_Recuo_Primeira_Linha"
    if f.alinhamento == "center" and f.maiusculas:
        return "Texto_Centralizado_Maiusculas_Negrito" if f.negrito else "Texto_Centralizado_Maiusculas"
    return None


def classe_de_tabela_por_formatacao(f: Formatacao, primeira_linha: bool) -> str | None:
    """Variante de fonte menor para parágrafos de célula, ou None.

    Tabela_Texto_10 é centralizada e Tabela_Texto_8 é alinhada à esquerda, então a
    fonte pequena só escolhe a classe quando o alinhamento também combina. No corpo da
    tabela, célula alinhada à direita (em geral números) mantém o alinhamento, que pesa
    mais. O cabeçalho é exceção: o conversor o centraliza (Tabela_Texto_Centralizado),
    qualquer que seja o alinhamento original, e com fonte pequena ele fica Tabela_Texto_10,
    também centralizada. Só um estilo com o nome de outra classe de tabela muda isso.
    """
    if f.tamanho_pt is None:
        return None
    if f.tamanho_pt <= FONTE_MAXIMA_TABELA_10_PT and (primeira_linha or f.alinhamento == "center"):
        return "Tabela_Texto_10"
    if f.tamanho_pt <= FONTE_MAXIMA_TABELA_8_PT and f.alinhamento in (None, "left", "justify"):
        return "Tabela_Texto_8"
    return None


def fonte_predominante(amostras: Iterable[tuple[float | None, int]]) -> float | None:
    """Tamanho de fonte que cobre mais texto, a partir de pares (tamanho, caracteres).

    Pesa pelo texto, e não pelo número de parágrafos: um documento com muitos títulos
    curtos em outra fonte continua tendo o corpo na fonte dos parágrafos longos.
    """
    pesos: Counter[float] = Counter()
    for tamanho, caracteres in amostras:
        if tamanho is not None and caracteres > 0:
            pesos[tamanho] += caracteres
    return pesos.most_common(1)[0][0] if pesos else None


def parece_citacao(f: Formatacao, fonte_do_corpo: float | None) -> bool:
    """Indica se o parágrafo tem a forma de uma citação longa: recuado e em fonte menor.

    Exige as duas marcas. A fonte é comparada com a do corpo, e não com um valor fixo:
    num documento todo em 10 pt, um parágrafo recuado nessa fonte não é citação.
    Centralizado ou à direita também não é: costuma ser legenda ou assinatura.
    """
    return (
        fonte_do_corpo is not None
        and f.tamanho_pt is not None
        and f.tamanho_pt < fonte_do_corpo
        and f.recuo_esquerdo_cm >= RECUO_MINIMO_CITACAO_CM
        and f.alinhamento in (None, "left", "justify")
    )


def _fecha_no_fim(texto: str, fecha: str) -> bool:
    """As aspas fecham uma vez só, e depois delas vêm só pontuação e a referência.

    Aspas fechadas no meio ("A" e "B") são falas curtas dentro do texto, e não citação.
    """
    if texto.count(fecha) != 1:
        return False
    return RE_DEPOIS_DAS_ASPAS.fullmatch(texto[texto.index(fecha) + 1 :]) is not None


def _fim_da_citacao(textos: list[str | None], inicio: int, abre: str, fecha: str) -> int | None:
    """Índice do parágrafo que fecha as aspas abertas antes de `inicio`, se houver.

    O parágrafo do meio pode reabrir as aspas, como manda a convenção da citação em
    vários parágrafos. Uma tabela (None) interrompe a busca, e aspas que fecham no meio
    de um parágrafo desfazem a citação.
    """
    for j in range(inicio, len(textos)):
        texto = textos[j]
        if texto is None:
            return None
        texto = texto.strip().removeprefix(abre)
        if fecha in texto:
            return j if _fecha_no_fim(texto, fecha) else None
    return None


def paragrafos_entre_aspas(textos: list[str | None]) -> set[int]:
    """Índices dos parágrafos que formam uma citação entre aspas com mais de uma linha.

    Recebe o texto de cada parágrafo, na ordem, sem os vazios, e None no lugar de cada
    tabela. A citação abre com aspas no começo de um parágrafo e fecha no fim dele ou
    de um dos seguintes. Num parágrafo só, o miolo precisa passar de uma linha (ou ter
    uma quebra dentro); em vários, já passa. A política fica aqui, e não em cada
    leitor, para Word e ODT marcarem os mesmos parágrafos.
    """
    membros: set[int] = set()
    i = 0
    while i < len(textos):
        texto = (textos[i] or "").strip()
        if not texto or texto[0] not in ASPAS:
            i += 1
            continue
        abre, fecha = texto[0], ASPAS[texto[0]]
        resto = texto[1:]
        if fecha in resto:
            miolo = resto[: resto.index(fecha)].strip()
            if _fecha_no_fim(resto, fecha) and ("\n" in miolo or len(miolo) >= MINIMO_LETRAS_CITACAO_ENTRE_ASPAS):
                membros.add(i)
            i += 1
            continue
        fim = _fim_da_citacao(textos, i + 1, abre, fecha)
        if fim is None:
            i += 1
            continue
        membros.update(range(i, fim + 1))
        i = fim + 1
    return membros


@dataclass
class CitacaoPorRecuo:
    """Pedido e contagem da citação pela forma: recuo com fonte menor, ou entre aspas.

    O nome vem da primeira regra; a das aspas veio depois e segue o mesmo pedido.
    Quem converte cria o objeto e diz se as regras se aplicam (`aplicar`). O leitor do
    formato preenche `fonte_do_corpo` antes de percorrer o documento e conta cada
    parágrafo com forma de citação, aplicando a classe ou não: em `encontradas` o
    recuado em fonte menor e em `entre_aspas` o que está numa citação entre aspas (que
    o leitor acha antes, por paragrafos_entre_aspas, porque ela pode ocupar vários
    parágrafos). As duas
    contagens ficam separadas para a interface dizer por que sugere a troca. O início
    de cada parágrafo fica em `trechos`, na ordem do documento, para quem decide ver o
    que muda sem procurar os parágrafos na prévia.
    """

    aplicar: bool = False
    fonte_do_corpo: float | None = None
    encontradas: int = 0
    entre_aspas: int = 0
    trechos: list[str] = field(default_factory=list)

    def classe(self, f: Formatacao, texto: str = "", entre_aspas: bool = False) -> str | None:
        """Conta o parágrafo com forma de citação e devolve "Citação" só se pedida.

        `entre_aspas` diz se o parágrafo está numa citação entre aspas. Centralizado ou à
        direita fica de fora, como na regra do recuo: costuma ser legenda ou epígrafe.
        """
        if parece_citacao(f, self.fonte_do_corpo):
            self.encontradas += 1
        elif entre_aspas and f.alinhamento in (None, "left", "justify"):
            self.entre_aspas += 1
        else:
            return None
        self.trechos.append(trecho_inicial(texto))
        return "Citação" if self.aplicar else None


PALAVRAS_DO_TRECHO = 12


def trecho_inicial(texto: str) -> str:
    """Primeiras palavras do parágrafo, o bastante para reconhecê-lo no documento."""
    palavras = texto.split()
    if len(palavras) <= PALAVRAS_DO_TRECHO:
        return " ".join(palavras)
    return " ".join(palavras[:PALAVRAS_DO_TRECHO]) + "…"


# Bloco de assinatura: as linhas centralizadas que fecham o documento saem sem a margem de
# 6 pt de Texto_Centralizado, que espaça demais o "[Assinado eletronicamente]", o nome e o
# cargo. Linha de assinatura é curta: acima disso, o parágrafo centralizado é texto. E tem
# ao menos nome e cargo: uma linha sozinha no fim é mais provavelmente legenda ou fecho.
CLASSE_ASSINATURA = "Tabela_Texto_Centralizado"
LIMITE_PALAVRAS_ASSINATURA = 12
MINIMO_LINHAS_ASSINATURA = 2


# Marca da assinatura eletrônica, com ou sem colchetes ou parênteses
RE_MARCA_ASSINATURA = re.compile(r"^[\[(]?\s*assinad[oa]\s+eletronicamente\s*[\])]?\.?$", re.IGNORECASE)
# Nome, cargo e unidade não terminam em pontuação; "De acordo." e "Encaminhe-se:" sim
RE_FIM_DE_FRASE = re.compile(r"[.,:;]$")


def linha_curta(texto: str) -> bool:
    """Curta o bastante para ser nome, cargo ou marca de assinatura."""
    return 0 < len(texto.split()) <= LIMITE_PALAVRAS_ASSINATURA


def pode_ser_linha_de_assinatura(texto: str, alinhamento: str | None) -> bool:
    """Centralizada e curta. Quem chama exclui título, lista, item e estilo explícito."""
    return alinhamento == "center" and linha_curta(texto)


def linhas_de_assinatura(candidatas: list[bool], curtas: list[str | None] | None = None) -> int:
    """Quantas linhas do fim formam o bloco de assinatura.

    Recebe, na ordem do documento, uma entrada por parágrafo com texto ou tabela (tabela
    é sempre falsa) e conta as verdadeiras do fim. Documento inteiro de linhas candidatas
    não tem bloco: seria o texto todo, e não uma assinatura.

    `curtas` traz, na mesma ordem, o texto de cada linha curta e sem classe própria, em
    qualquer alinhamento (None nas outras). Com ela, o bloco também pode começar na marca
    "[assinado eletronicamente]" e ir até o fim: o texto colado de um chat ou de um .txt
    não tem centralização, mas a marca, o nome e o cargo dizem o que é a assinatura. O
    "Atenciosamente," antes da marca fica de fora.
    """
    n = 0
    for candidata in reversed(candidatas):
        if not candidata:
            break
        n += 1
    if n == len(candidatas) or n < MINIMO_LINHAS_ASSINATURA:
        n = 0
    if curtas:
        finais = 0
        for texto in reversed(curtas):
            if texto is None:
                break
            finais += 1
        trecho = curtas[len(curtas) - finais :]
        # A primeira marca depois da qual só há marcas, nomes e cargos: um "De acordo." entre
        # duas assinaturas deixa a primeira para indices_de_assinatura, como bloco do meio
        marca = next(
            (
                i
                for i, texto in enumerate(trecho)
                if RE_MARCA_ASSINATURA.match(texto or "")
                and not any(
                    RE_FIM_DE_FRASE.search(t or "") and not RE_MARCA_ASSINATURA.match(t or "") for t in trecho[i:]
                )
            ),
            None,
        )
        if marca is not None:
            pela_marca = finais - marca
            if MINIMO_LINHAS_ASSINATURA <= pela_marca < len(curtas):
                n = max(n, pela_marca)
    return n


# Linhas de uma assinatura do meio do documento depois da marca, quando não há
# centralização para dizer onde ela termina: nome, cargo, unidade e órgão
MAXIMO_LINHAS_DEPOIS_DA_MARCA = 4


def indices_de_assinatura(candidatas: list[bool], curtas: list[str | None] | None = None) -> set[int]:
    """Posições das linhas que formam blocos de assinatura, no fim ou no meio do documento.

    O bloco do fim segue linhas_de_assinatura. No meio, o bloco precisa começar na marca
    "[assinado eletronicamente]": a nota assinada pelo coordenador e, depois do "De
    acordo.", pela diretora tem duas assinaturas, e só a do fim era reconhecida. Sem a
    marca, linhas centralizadas no meio são título ou destaque, e não assinatura.

    Depois da marca centralizada, o bloco segue pelas linhas candidatas (centralizadas e
    curtas). Com a marca sem centralização (texto colado, .txt), segue pelas linhas
    curtas que não terminam em pontuação, até MAXIMO_LINHAS_DEPOIS_DA_MARCA: é o que
    separa o cargo do "De acordo." da linha seguinte.
    """
    total = len(candidatas)
    n = linhas_de_assinatura(candidatas, curtas)
    indices = set(range(total - n, total))
    if not curtas:
        return indices
    i = 0
    while i < total - n:
        marca = curtas[i]
        if marca is None or not RE_MARCA_ASSINATURA.match(marca):
            i += 1
            continue
        fim = i + 1
        if candidatas[i]:
            while fim < total and candidatas[fim]:
                fim += 1
        else:
            while (
                fim < total
                and fim - i <= MAXIMO_LINHAS_DEPOIS_DA_MARCA
                and (texto := curtas[fim]) is not None
                and not RE_MARCA_ASSINATURA.match(texto)
                and not RE_FIM_DE_FRASE.search(texto)
            ):
                fim += 1
        # O bloco do meio que encosta no do fim é o mesmo bloco, já contado
        if fim - i >= MINIMO_LINHAS_ASSINATURA and fim < total:
            indices.update(range(i, fim))
        i = max(fim, i + 1)
    return indices
