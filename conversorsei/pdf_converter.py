"""
pdf_converter.py — Extração de texto de PDFs, limpeza de boilerplate SEI e conversão para HTML SEI.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from conversorsei.entrada import FonteDocumento, abrir_binario, nome_da_fonte
from conversorsei.md_converter import converter_texto_md_para_blocos, escapar_markdown

# ---------------------------------------------------------------------------
# Extração bruta de texto (pdftotext prioritário, pypdf como fallback)
# ---------------------------------------------------------------------------

def extrair_texto_pdf(pdf_path: FonteDocumento) -> str:
    """Extrai texto bruto de um PDF, vindo de arquivo ou de memória."""
    nome = nome_da_fonte(pdf_path, "documento.pdf")

    # O pdftotext é um programa externo e só sabe ler do disco. Quando o documento chega
    # em memória (a interface web), a extração fica com o pypdf, que lê de um stream.
    if isinstance(pdf_path, (str, Path)) and shutil.which("pdftotext"):
        out = subprocess.run(
            ["pdftotext", "-nopgbrk", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            # O pdftotext escreve UTF-8, mas sem `encoding` o Python decodifica pela
            # página de código do sistema (cp1252 no Windows) e os acentos se perdem.
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout

    # Fallback: pypdf
    try:
        from pypdf import PdfReader

        with abrir_binario(pdf_path) as binario:
            reader = PdfReader(binario)
            texto = "\n".join(_texto_da_pagina(page) for page in reader.pages)
    except Exception as e:
        raise RuntimeError(f"Falha ao extrair texto do PDF {nome}: {e}") from e

    if not texto.strip():
        # Sem camada de texto não há o que converter, e o erro genérico ("nenhum
        # conteúdo extraído") parece defeito da ferramenta
        raise RuntimeError(
            f"O PDF {nome} não tem camada de texto: provavelmente é um documento digitalizado. "
            "Passe o arquivo por OCR antes de converter."
        )
    return texto


def _texto_da_pagina(page) -> str:
    """Texto de uma página com o pypdf, preferindo o modo que respeita o layout.

    O modo padrão parte palavras no meio ("d e autoria", "a ltera") em PDFs
    justificados, como os do SEI. O modo "layout" preserva o espaçamento original.
    """
    try:
        texto = page.extract_text(extraction_mode="layout")
        if texto and texto.strip():
            return texto
    except Exception:
        pass
    return page.extract_text() or ""


# ---------------------------------------------------------------------------
# Limpeza de boilerplate SEI (assinaturas eletrônicas, código CRC, etc.)
# ---------------------------------------------------------------------------

_ASSINATURA = re.compile(
    r"Documento assinado eletronicamente por.*?"
    r"(?:c[oó]digo\s+CRC\s+[0-9A-F]+\.?|Decreto\s+n[º°]\s*10\.543[^\n]*\.)",
    re.IGNORECASE | re.DOTALL,
)
_AUTENTICIDADE = re.compile(
    r"A autenticidade do documento pode ser conferida.*?"
    r"(?:c[oó]digo\s+CRC\s+[0-9A-F]+\.?|informando[^\n]*\.)",
    re.IGNORECASE | re.DOTALL,
)
# Rodapé impresso pelo SEI em toda página ("Nota Técnica 110 (6900388)   SEI 80000.../ pg. 1").
# Sem removê-lo, o texto do rodapé entra no meio da frase que a página cortou. As linhas
# em branco ao redor entram junto: a frase precisa emendar direto na página seguinte, ou
# a quebra de página parte o parágrafo em dois.
_RODAPE_PAGINA = re.compile(
    r"(?:\n[ \t]*)*\n[^\n]*?SEI\s+[\d./_\-]+\s*/\s*pg\.\s*\d+[ \t]*(?:\n[ \t]*)*",
    re.IGNORECASE,
)
# Tipos documentais do SEI cujo cabeçalho residual ("Despacho 6900388") sobra na
# extração. A lista cobre os documentos mais frequentes na Administração Pública.
TIPOS_DOCUMENTAIS = (
    r"Despacho|Nota\s+T[eé]cnica|Of[ií]cio|Parecer|Memorando|Portaria|Informa[cç][aã]o"
    r"|Relat[oó]rio|Edital|Ata|Termo\s+de\s+Refer[eê]ncia|Decis[aã]o|Instru[cç][aã]o\s+Normativa"
    r"|Comunica[cç][aã]o\s+Interna|Circular|Resolu[cç][aã]o|Certid[aã]o|Declara[cç][aã]o|Manifesta[cç][aã]o"
)

_LINHAS_LIXO = re.compile(
    r"^\s*([\[(]\s*(?:assinatura eletr[oô]nica|assinado eletronicamente)\s*[\])]"
    r"|Refer[eê]ncia:\s*(?:Caso responda|Processo\s+n[º°])[^\n]*"
    r"|SEI\s+[0-9./_\-]+\s*/\s*pg\.\s*\d+"
    r"|(?:" + TIPOS_DOCUMENTAIS + r")\s+\d{6,8})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def limpar_boilerplate_sei(texto: str) -> str:
    """Remove assinaturas eletrônicas, carimbos de conformidade e cabeçalhos residuais do SEI."""
    texto = _ASSINATURA.sub("", texto)
    texto = _AUTENTICIDADE.sub("", texto)
    texto = _RODAPE_PAGINA.sub("\n", texto)
    texto = _LINHAS_LIXO.sub("", texto)

    linhas = [ln.rstrip() for ln in texto.splitlines()]
    linhas = [ln.lstrip() if ln.strip() else "" for ln in linhas]
    texto = "\n".join(linhas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() + "\n"


# ---------------------------------------------------------------------------
# Estruturação do texto extraído para Markdown
# ---------------------------------------------------------------------------

# Linha inteira em caixa alta: título de seção ("CONCLUSÃO") ou nome de quem assina
# ("MARIA ROSA TESSER R. LIMA"), que o SEI também apresenta centralizado e em negrito.
RE_SECAO_MAIUSCULA = re.compile(r"^([A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇ][A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇ\s.\-]{2,})$")
# Item numerado já remontado, com o texto na mesma linha ("1.1. Trata-se de ...").
RE_ITEM = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.\s+(\S.*)$")
# Pedaço de numeração isolado numa linha. Extratores de PDF quebram "1.1." em "1", ".",
# "1", "."; o pdftotext deixa "1.1." sozinho, com o texto do item na linha seguinte.
RE_FRAGMENTO_NUM = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})*\.?|\.)$")
LIMITE_TITULO = 60

def remontar_numeracao(linhas: list[str]) -> list[str]:
    """Traz a numeração do item e o texto que ela abre para a mesma linha."""
    saida: list[str] = []
    numero = ""
    for ln in linhas:
        if RE_FRAGMENTO_NUM.match(ln):
            numero += ln
            continue
        if not ln:
            # Linha em branco entre a numeração e o texto do item não separa nada
            if not numero:
                saida.append("")
            continue
        saida.append(f"{numero} {ln}" if numero else ln)
        numero = ""
    if numero:
        saida.append(numero)
    return saida


def e_seccao_maiuscula(linha: str) -> bool:
    """Indica se a linha é um título de seção sem numeração ("CONCLUSÃO")."""
    return bool(RE_SECAO_MAIUSCULA.match(linha)) and len(linha) <= LIMITE_TITULO


def reagrupar_paragrafos(linhas: list[str]) -> list[tuple[str, str]]:
    """Desfaz a quebra de linha do PDF, devolvendo ("cabecalho"|"corpo", parágrafo).

    O extrator quebra a frase em várias linhas e nem sempre deixa linha em branco
    entre os parágrafos, então a quebra real é reconhecida pela estrutura: no corpo
    do documento, cada item numerado ou título de seção abre um parágrafo e as demais
    linhas são continuação.

    O cabeçalho vem antes de tudo isso (órgão, unidade, número do documento e do
    processo) e tem uma linha por parágrafo. Termina no primeiro item numerado ou na
    primeira linha em branco, o que vier primeiro.
    """
    paragrafos: list[tuple[str, str]] = []
    atual: list[str] = []
    cabecalho = True

    def fechar() -> None:
        if atual:
            paragrafos.append(("corpo", re.sub(r"\s+", " ", " ".join(atual)).strip()))
            atual.clear()

    for ln in linhas:
        if not ln:
            fechar()
            cabecalho = False
            continue
        if RE_ITEM.match(ln):
            fechar()
            cabecalho = False
            atual.append(ln)
            continue
        if cabecalho:
            fechar()
            paragrafos.append(("cabecalho", ln))
            continue
        if e_seccao_maiuscula(ln):
            fechar()
            paragrafos.append(("corpo", ln))
            continue
        atual.append(ln)

    fechar()
    return paragrafos


def estruturar_texto_para_markdown(texto: str) -> str:
    """Transforma texto limpo de PDF em Markdown formatado com títulos e parágrafos estruturados."""
    linhas = remontar_numeracao([ln.strip() for ln in texto.splitlines()])
    md_linhas = []

    for tipo, p in reagrupar_paragrafos(linhas):
        # A estrutura ("#", "<p class=...>") é nossa e vai crua; só o texto do PDF é escapado
        texto = escapar_markdown(p)

        if tipo == "cabecalho":
            # Órgão, unidade e identificação do documento: centralizados, como no SEI
            md_linhas.append(f'<p class="Texto_Centralizado">{texto}</p>\n')
            continue

        m = RE_ITEM.match(p)
        if m and e_seccao_maiuscula(m.group(2)):
            # Item de título ("1. ASSUNTO"): o número fica, o SEI é quem renumera
            prof = m.group(1).count(".") + 1
            md_linhas.append(f'{"#" * min(prof, 4)} {texto}\n')
            continue

        if e_seccao_maiuscula(p):
            md_linhas.append(f"## {texto}\n")
            continue

        md_linhas.append(f"{texto}\n")

    return "\n".join(md_linhas)


def converter_pdf_para_blocos(pdf_path: FonteDocumento, max_nivel: int = 4) -> list[str]:
    """Extrai, limpa, estrutura e converte um arquivo PDF para blocos HTML SEI."""
    texto_bruto = extrair_texto_pdf(pdf_path)
    texto_limpo = limpar_boilerplate_sei(texto_bruto)
    md_content = estruturar_texto_para_markdown(texto_limpo)
    return converter_texto_md_para_blocos(md_content, max_nivel=max_nivel, extraido=True)


def converter_pdf_para_html(pdf_path: FonteDocumento, max_nivel: int = 4) -> str:
    """Converte arquivo PDF e retorna o HTML do corpo consolidado."""
    blocos = converter_pdf_para_blocos(pdf_path, max_nivel=max_nivel)
    return "\n".join(blocos)
