"""
particionador.py — Gerencia montagem de HTML institucional, divisão em partes
e orçamento de tamanho para inserção no SEI (SEI Pro / CKEditor).
"""
from __future__ import annotations

import re
from pathlib import Path

from conversao_sei.recursos import obter_estilos_sei

# Limite em bytes a partir do qual o plugin SEI Pro perde estilos ao colar
LIMITE_SEI_BYTES = 27_000
MAX_KB_PADRAO = 22
# 1 KB = 1.000 bytes em todo o projeto, para o tamanho exibido bater com o limite aplicado
BYTES_POR_KB = 1000

# Contadores CSS usados pelas classes institucionais do SEI
NOMES_CONTADORES = (
    "item-n1",
    "item-n2",
    "item-n3",
    "item-n4",
    "paragrafo-n1",
    "paragrafo-n2",
    "paragrafo-n3",
    "romano_maiusculo",
    "letra_minuscula",
)

# Para cada classe: contador incrementado e contadores zerados, espelhando estilos_sei.css
EFEITO_NOS_CONTADORES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Item_Nivel1": ("item-n1", ("item-n2", "item-n3", "item-n4", "romano_maiusculo", "letra_minuscula")),
    "Item_Nivel2": ("item-n2", ("item-n3", "item-n4", "romano_maiusculo", "letra_minuscula")),
    "Item_Nivel3": ("item-n3", ("item-n4", "romano_maiusculo", "letra_minuscula")),
    "Item_Nivel4": ("item-n4", ("romano_maiusculo", "letra_minuscula")),
    "Paragrafo_Numerado_Nivel1": ("paragrafo-n1", ("paragrafo-n2", "paragrafo-n3", "romano_maiusculo", "letra_minuscula")),
    "Paragrafo_Numerado_Nivel2": ("paragrafo-n2", ("paragrafo-n3", "romano_maiusculo", "letra_minuscula")),
    "Paragrafo_Numerado_Nivel3": ("paragrafo-n3", ("romano_maiusculo", "letra_minuscula")),
    "Item_Inciso_Romano": ("romano_maiusculo", ("letra_minuscula",)),
    "Item_Alinea_Letra": ("letra_minuscula", ()),
}

RE_CLASSE = re.compile(r'class="([^"]+)"')


def contadores_zerados() -> dict[str, int]:
    """Estado inicial dos contadores CSS (todos em zero)."""
    return dict.fromkeys(NOMES_CONTADORES, 0)


def avancar_contadores(estado: dict[str, int], corpo_html: str) -> dict[str, int]:
    """Simula o efeito do corpo sobre os contadores CSS e devolve o novo estado.

    Permite que a parte seguinte continue a numeração de onde a anterior parou,
    em vez de recomeçar do 1 na prévia pelo navegador.
    """
    novo = {**contadores_zerados(), **estado}
    for atributo in RE_CLASSE.findall(corpo_html):
        efeito = EFEITO_NOS_CONTADORES.get(atributo)
        if efeito is None:
            continue
        incrementado, zerados = efeito
        novo[incrementado] = novo.get(incrementado, 0) + 1
        for nome in zerados:
            novo[nome] = 0
    return novo


def formatar_counter_reset(contadores: dict[str, int] | None = None) -> str:
    """Monta o valor da propriedade counter-reset a partir do estado dos contadores."""
    estado = {**contadores_zerados(), **(contadores or {})}
    return " ".join(f"{nome} {estado.get(nome, 0)}" for nome in NOMES_CONTADORES)


def css_institucional() -> str:
    """Retorna o conteúdo do CSS institucional (34 classes oficiais do SEI)."""
    return obter_estilos_sei()


def montar_html(corpo_html: str, css: str | None = None, contadores: dict[str, int] | None = None) -> str:
    """Envolve o corpo em um documento HTML com CSS institucional e contadores para preview.

    `contadores` recebe o estado acumulado das partes anteriores, para que a numeração
    da prévia continue em sequência.
    """
    css_content = css if css is not None else css_institucional()
    counter_reset = formatar_counter_reset(contadores)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Conteúdo formatado para o SEI</title>
<style>
body {{font-family:Calibri, sans-serif; font-size:12pt; color:#000; background:#fff;
      max-width:19cm; margin:1.5em auto; padding:0 1em;
      counter-reset:{counter_reset};}}
table {{border-collapse:collapse;}}
ul {{margin:6pt 6pt 6pt 40px; padding-left:20px;}}
li {{font-size:12pt; font-family:Calibri; text-align:justify; margin:3pt 0;}}
{css_content}
</style>
</head>
<body>
<!-- ============================================================
     COMO USAR (este comentário NÃO é copiado):
     1. Abra este arquivo no Chrome / navegador
     2. Cmd+A (selecionar tudo) e Cmd+C (copiar)
     3. No editor do documento SEI, clique no corpo e Cmd+V
     4. Confira a numeração automática e as tabelas; depois Salvar
     ============================================================ -->
{corpo_html}
</body>
</html>
"""


def orcamento_corpo(max_kb: int = MAX_KB_PADRAO, so_corpo: bool = False) -> int:
    """Calcula quantos bytes do alvo podem ser usados pelo corpo de cada parte."""
    alvo = max_kb * BYTES_POR_KB
    if so_corpo:
        return alvo
    # Contadores com valores altos para que o overhead considerado seja o do pior caso
    overhead = len(montar_html("", contadores=dict.fromkeys(NOMES_CONTADORES, 9999)).encode("utf-8"))
    return max(1000, alvo - overhead)


# Estrutura da tabela montada pelo conversor de DOCX (ver montar_tabela_html)
RE_TABELA = re.compile(r"^(<table\b[^>]*>\s*<tbody>)(.*?)(</tbody>\s*</table>)$", re.DOTALL)
RE_LINHA_TABELA = re.compile(r"<tr>.*?</tr>", re.DOTALL)
RE_ROWSPAN = re.compile(r'rowspan="(\d+)"')


def alcance_da_linha(linha_html: str, indice: int) -> int:
    """Índice da última linha coberta pelas células mescladas que começam nesta linha."""
    spans = [int(n) for n in RE_ROWSPAN.findall(linha_html)]
    return indice + max(spans, default=1) - 1


def dividir_tabela(bloco: str, max_bytes: int) -> list[str]:
    """Quebra uma tabela em tabelas menores, repetindo a linha de cabeçalho em cada uma.

    Uma tabela é um bloco só, então sem esta quebra uma tabela longa produz sozinha uma
    parte acima do orçamento, e o SEI descarta os estilos na colagem.

    O corte só acontece onde nenhuma célula mesclada atravessa a fronteira: partir um
    rowspan deixaria a tabela torta. Onde não existe corte seguro, a parte passa do
    limite, o que é melhor do que entregar tabela quebrada. Bloco que não seja tabela
    volta intacto.
    """
    m = RE_TABELA.match(bloco.strip())
    if not m:
        return [bloco]

    abertura, miolo, fechamento = m.groups()
    linhas = RE_LINHA_TABELA.findall(miolo)
    if len(linhas) < 2:
        return [bloco]

    # O cabeçalho pode ocupar mais de uma linha, quando suas células têm rowspan
    fim_cabecalho = alcance_da_linha(linhas[0], 0)
    cabecalho = linhas[: fim_cabecalho + 1]
    corpo = linhas[fim_cabecalho + 1 :]
    if not corpo:
        return [bloco]

    def montar(linhas_parte: list[str]) -> str:
        return abertura + "\n" + "\n".join(cabecalho + linhas_parte) + "\n" + fechamento

    bytes_fixos = len(montar([]).encode("utf-8"))
    partes: list[str] = []
    atual: list[str] = []
    tam = 0
    ultima_coberta = -1

    for i, linha in enumerate(corpo):
        lb = len(linha.encode("utf-8")) + 1
        corte_seguro = bool(atual) and i > ultima_coberta
        if corte_seguro and bytes_fixos + tam + lb > max_bytes:
            partes.append(montar(atual))
            atual, tam = [], 0
        atual.append(linha)
        tam += lb
        ultima_coberta = max(ultima_coberta, alcance_da_linha(linha, i))

    if atual:
        partes.append(montar(atual))
    return partes


def blocos_no_limite(bloco: str, max_bytes: int) -> list[str]:
    """Devolve o bloco, ou os pedaços dele, quando sozinho já estoura o limite."""
    if len(bloco.encode("utf-8")) <= max_bytes:
        return [bloco]
    return dividir_tabela(bloco, max_bytes)


def dividir_em_partes(blocos: list[str], max_bytes: int) -> list[list[str]]:
    """Agrupa blocos em partes com no máximo `max_bytes` cada.

    Um bloco maior que o limite é quebrado quando é tabela. Não sendo tabela (um
    parágrafo enorme), fica sozinho na sua parte, ainda acima do limite.
    """
    partes: list[list[str]] = []
    atual: list[str] = []
    tam = 0
    for bloco in blocos:
        for b in blocos_no_limite(bloco, max_bytes):
            lb = len(b.encode("utf-8"))
            if atual and tam + lb > max_bytes:
                partes.append(atual)
                atual, tam = [], 0
            atual.append(b)
            tam += lb
    if atual:
        partes.append(atual)
    return partes


def limpar_saidas_antigas(saida: str | Path, gerar_partes: bool) -> list[Path]:
    """Remove saídas antigas conflitantes (mantém mutuamente exclusivos arquivo único e partes)."""
    caminho = Path(saida)
    base = caminho.stem
    ext = caminho.suffix
    pasta = caminho.parent

    removidos: list[Path] = []
    for f in pasta.glob(f"{base}_parte*{ext}"):
        try:
            f.unlink()
            removidos.append(f)
        except OSError:
            pass

    if gerar_partes and caminho.is_file():
        try:
            caminho.unlink()
            removidos.append(caminho)
        except OSError:
            pass

    return removidos


def derivar_caminho_saida(
    entrada: str | Path,
    so_corpo: bool = False,
    outdir: str | Path | None = None,
) -> Path:
    """Deriva o caminho do arquivo de saída SEI a partir da entrada."""
    p_in = Path(entrada)
    stem = p_in.stem

    if stem.startswith("Nota_Tecnica_Revisada_"):
        identificador = stem[len("Nota_Tecnica_Revisada_"):]
        base_saida = f"Nota_Tecnica_SEI_{identificador}"
    elif stem.startswith("Nota_Tecnica_"):
        identificador = stem[len("Nota_Tecnica_"):]
        base_saida = f"Nota_Tecnica_SEI_{identificador}"
    else:
        base_saida = f"{stem}_SEI"

    sufixo = "_corpo.html" if so_corpo else ".html"
    destino_pasta = Path(outdir) if outdir else p_in.parent
    return destino_pasta / f"{base_saida}{sufixo}"
