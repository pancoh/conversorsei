"""
validador.py — Validação de conformidade do HTML gerado com os padrões do SEI.
"""
from __future__ import annotations

import re
from pathlib import Path

from conversorsei.recursos import obter_estilos_sei

CLASSES_VALIDAS_SEI = {
    "Citação",
    "Fonte_Calibri",
    "Item_Alinea_Letra",
    "Item_Inciso_Romano",
    "Item_Nivel1",
    "Item_Nivel2",
    "Item_Nivel3",
    "Item_Nivel4",
    "Paragrafo_Numerado_Nivel1",
    "Paragrafo_Numerado_Nivel2",
    "Paragrafo_Numerado_Nivel3",
    "Tabela_Texto_10",
    "Tabela_Texto_8",
    "Tabela_Texto_Alinhado_Direita",
    "Tabela_Texto_Alinhado_Esquerda",
    "Tabela_Texto_Centralizado",
    "Tachado",
    "Texto_Alinhado_Direita",
    "Texto_Alinhado_Esquerda",
    "Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc",
    "Texto_Alinhado_Esquerda_Espaçamento_Simples",
    "Texto_Centralizado",
    "Texto_Centralizado_Maiusculas",
    "Texto_Centralizado_Maiusculas_Negrito",
    "Texto_Citação",
    "Texto_Ementa",
    "Texto_Espaco_Duplo_Recuo_Primeira_Linha",
    "Texto_Fundo_Cinza_Maiusculas_Negrito",
    "Texto_Fundo_Cinza_Negrito",
    "Texto_Justificado",
    "Texto_Justificado_Maiusculas",
    "Texto_Justificado_Recuo_Primeira_Linha",
    "Texto_Justificado_Recuo_Primeira_Linha2",
    "Texto_Mono_Espaçado",
}


def obter_classes_validas_css() -> set[str]:
    """Extrai classes p.NomeClasse da folha de estilos institucional."""
    css = obter_estilos_sei()
    if not css:
        return set(CLASSES_VALIDAS_SEI)
    classes = set(re.findall(r"p\.([^\s{,:]+)", css))
    return classes or set(CLASSES_VALIDAS_SEI)


def extrair_corpo_html(html: str) -> str:
    """Extrai apenas o conteúdo do <body> se presente."""
    if "<body>" in html and "</body>" in html:
        return html.split("<body>", 1)[1].split("</body>", 1)[0]
    return html


NOME_DA_NUMERACAO = {
    "Item_Nivel": "A numeração dos títulos e itens",
    "Paragrafo_Numerado_Nivel": "A numeração dos parágrafos numerados",
}


def verificar_sequencia_de_niveis(corpo: str, prefixo: str) -> list[str]:
    """Confere se os níveis de uma família de classes numeradas abrem e avançam de um em um.

    O contador do SEI é aninhado: um Item_Nivel2 sem Item_Nivel1 antes numera "0.1", e
    pular de nível 1 para 3 deixa um dos contadores em zero. Vale igual para os
    parágrafos numerados, que têm a própria família de contadores.
    """
    niveis = [int(c) for c in re.findall(rf'class="{prefixo}(\d)"', corpo)]
    if not niveis:
        return []

    # O nome da família vai na mensagem: sem ele, as duas numerações geram o mesmo texto
    # e não se sabe qual conferir
    numeracao = NOME_DA_NUMERACAO.get(prefixo, "A numeração")
    falhas = []
    if niveis[0] != 1:
        falhas.append(f"{numeracao} começa no nível {niveis[0]}. Confira se falta um item do nível 1.")
    anterior = niveis[0]
    for n in niveis[1:]:
        if n > anterior + 1:
            falhas.append(
                f"{numeracao} salta do nível {anterior} para o {n}. Confira se falta um item intermediário."
            )
            break
        anterior = n
    return falhas


def validar_html_sei(html: str, origem_markdown: bool = True) -> list[str]:
    """Verifica se o HTML atende estritamente às regras do editor do SEI.

    `origem_markdown` falso (entrada .txt, .docx, .odt ou .pdf) desliga o aviso de
    "```" sem fechamento: fora do Markdown, ele é texto do documento.

    Retorna lista de problemas encontrados (vazia se estiver 100% válido).
    """
    falhas: list[str] = []
    b = extrair_corpo_html(html)

    # 1. Classes permitidas
    classes_validas = obter_classes_validas_css()
    usadas = set(re.findall(r'class="([^"]+)"', b))
    invalidas = usadas - classes_validas
    if invalidas:
        descricao = (
            "um estilo de parágrafo que o SEI não reconhece" if len(invalidas) == 1
            else f"{len(invalidas)} estilos de parágrafo que o SEI não reconhece"
        )
        falhas.append(
            f"O documento usa {descricao}. "
            "Confira a formatação desses trechos no documento convertido."
        )

    # 2. Sintaxe residual Markdown. Bloco de código é conteúdo literal: link, "---" e
    # "```" ali não são marcação que sobrou
    b_sem_codigo = re.sub(r'<p class="Texto_Mono_Espaçado">.*?</p>', "", b, flags=re.DOTALL)
    if re.search(r"\[[^\]]+\]\(https?://", b_sem_codigo):
        falhas.append("Um link ficou como texto em vez de funcionar. Confira o endereço no documento convertido.")
    if re.search(r">\s*[-–—]{3,}\s*<", b_sem_codigo):
        falhas.append("Uma linha separadora ficou como texto. Confira esse trecho no documento convertido.")
    # Aviso só para a cerca ```. Não há aviso para ">" no início nem para "~~texto~~": no
    # .md, o que sobra deles é quase sempre marca que o autor escapou de propósito, e o
    # aviso anterior dava alarme falso nesse caso. Os poucos casos em que o conversor deixa
    # a marca (riscado que atravessa um link, ">" dentro de <red>) ficam sem aviso.
    if origem_markdown and "```" in b_sem_codigo:
        falhas.append("Uma marca de bloco de código ficou no texto. Confira as linhas com três crases.")

    # 3. Corrupção de URLs
    if "ccivil<em>" in b or re.search(r"<em>[^<]*</em>\d", b):
        falhas.append("Um endereço de internet pode ter sido alterado pela formatação. Confira o link no original.")

    # 4. Tags proibidas no corpo do SEI
    if re.search(r"<(h[1-6]|div|iframe|script)\b", b, re.IGNORECASE):
        falhas.append("O documento contém estrutura que o editor do SEI não aceita. Confira a prévia antes de colar.")

    # 5. Numeração automática
    for prefixo in ("Item_Nivel", "Paragrafo_Numerado_Nivel"):
        falhas.extend(verificar_sequencia_de_niveis(b, prefixo))

    # 6. Itens de lista sem classe institucional
    if re.search(r"<li(?![^>]*\sclass=)", b, re.IGNORECASE):
        falhas.append("Um item de lista pode perder a formatação no SEI. Confira a lista após colar.")

    return falhas


def validar_arquivo_sei(caminho: str | Path) -> list[str]:
    """Lê um arquivo HTML do disco e valida."""
    p = Path(caminho)
    if not p.is_file():
        return [f"Arquivo não encontrado: {caminho}"]
    conteudo = p.read_text(encoding="utf-8", errors="replace")
    return validar_html_sei(conteudo)
