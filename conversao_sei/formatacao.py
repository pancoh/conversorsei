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

A citação pelo recuo e pela fonte menor é a exceção, e só vale a pedido
(CitacaoPorRecuo). Documento real quase nunca usa estilo, e a citação costuma vir só
recuada e em fonte menor. A conversão conta esses parágrafos e deixa quem converte
decidir: a interface oferece a troca, em vez de a regra adivinhar sozinha.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from conversao_sei.validador import obter_classes_validas_css

# Tabela_Texto_8 e Tabela_Texto_10 são as variantes em fonte menor das células
FONTE_MAXIMA_TABELA_8_PT = 8.0
FONTE_MAXIMA_TABELA_10_PT = 10.0
# Menos que isso ("I", "OK") não basta para dizer que o parágrafo está em caixa alta
MINIMO_LETRAS_MAIUSCULAS = 3
# A ABNT pede 4 cm para a citação longa. Metade disso já não acontece por acaso num
# parágrafo comum, e deixa folga para modelos com recuo menor
RECUO_MINIMO_CITACAO_CM = 2.0


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


@dataclass
class CitacaoPorRecuo:
    """Pedido e contagem da citação pelo recuo e pela fonte menor.

    Quem converte cria o objeto e diz se a regra se aplica (`aplicar`). O leitor do
    formato preenche `fonte_do_corpo` antes de percorrer o documento e conta cada
    parágrafo com forma de citação em `encontradas`, aplicando a classe ou não. A
    contagem é o que permite à interface oferecer a troca quando a regra está desligada.
    O início de cada parágrafo fica em `trechos`, para quem decide ver o que muda sem
    procurar os parágrafos na prévia.
    """

    aplicar: bool = False
    fonte_do_corpo: float | None = None
    encontradas: int = 0
    trechos: list[str] = field(default_factory=list)

    def classe(self, f: Formatacao, texto: str = "") -> str | None:
        """Conta o parágrafo com forma de citação e devolve "Citação" só se pedida."""
        if not parece_citacao(f, self.fonte_do_corpo):
            return None
        self.encontradas += 1
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


def pode_ser_linha_de_assinatura(texto: str, alinhamento: str | None) -> bool:
    """Centralizada e curta. Quem chama exclui título, lista, item e estilo explícito."""
    return alinhamento == "center" and 0 < len(texto.split()) <= LIMITE_PALAVRAS_ASSINATURA


def linhas_de_assinatura(candidatas: list[bool]) -> int:
    """Quantas linhas do fim formam o bloco de assinatura.

    Recebe, na ordem do documento, uma entrada por parágrafo com texto ou tabela (tabela
    é sempre falsa) e conta as verdadeiras do fim. Documento inteiro de linhas candidatas
    não tem bloco: seria o texto todo, e não uma assinatura.
    """
    n = 0
    for candidata in reversed(candidatas):
        if not candidata:
            break
        n += 1
    if n == len(candidatas) or n < MINIMO_LINHAS_ASSINATURA:
        return 0
    return n
