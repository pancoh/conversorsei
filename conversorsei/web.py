"""
web.py — Funções auxiliares para conversão em memória utilizadas na interface Web (Pyodide/WASM).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conversorsei.core import converter_bytes
from conversorsei.particionador import BYTES_POR_KB, LIMITE_SEI_BYTES, MAX_KB_PADRAO


def nome_seguro(nome_arquivo: str) -> str:
    """Reduz o nome recebido ao componente final, sem qualquer parte de caminho.

    A conversão não grava nada em disco, mas o nome vai para o arquivo que o navegador
    baixa: um '../evil.md' que sobrevivesse até ali seria um caminho de escrita fora da
    pasta de downloads. Aceita separadores POSIX e Windows.
    """
    bruto = (nome_arquivo or "").replace("\\", "/").strip()
    nome = Path(bruto).name.strip()
    if not nome or nome in {".", ".."}:
        raise ValueError(f"Nome de arquivo inválido: {nome_arquivo!r}")
    return nome


def converter_documento_memoria(
    nome_arquivo: str,
    conteudo_bytes: bytes,
    so_corpo: bool = False,
    forcar_unico: bool = False,
    forcar_partes: bool = False,
    max_kb: int = MAX_KB_PADRAO,
    max_nivel: int = 4,
    validar: bool = True,
    citacao_por_recuo: bool = False,
    omitir_cabecalho: bool = False,
    texto_reconhecido: str | None = None,
) -> dict[str, Any]:
    """Converte bytes de um arquivo em memória e retorna um dicionário com os arquivos gerados."""
    resultado = converter_bytes(
        nome_arquivo=nome_seguro(nome_arquivo),
        conteudo=conteudo_bytes,
        so_corpo=so_corpo,
        forcar_unico=forcar_unico,
        forcar_partes=forcar_partes,
        max_kb=max_kb,
        max_nivel=max_nivel,
        validar=validar,
        citacao_por_recuo=citacao_por_recuo,
        omitir_cabecalho=omitir_cabecalho,
        texto_reconhecido=texto_reconhecido,
    )

    arquivos = [
        {
            "nome": arquivo.nome,
            "conteudo": arquivo.conteudo,
            "tamanho_bytes": arquivo.tamanho_bytes,
            "tamanho_kb": round(arquivo.tamanho_bytes / BYTES_POR_KB, 2),
            # A interface diz se o arquivo cabe numa colagem: o número sozinho não diz
            # se 21 KB é pouco ou muito, e com "forçar arquivo único" ele pode passar
            "cabe_no_limite": arquivo.tamanho_bytes <= LIMITE_SEI_BYTES,
        }
        for arquivo in resultado.arquivos
    ]

    return {
        "sucesso": resultado.sucesso,
        # O nome de origem acompanha o resultado: no modo em lote, dois documentos podem
        # gerar a mesma saída (nota.odt e nota.docx viram nota_SEI.html) e a interface
        # precisa separá-los sem ter de guardar o nome por fora
        "nome_origem": resultado.nome_origem,
        "erros": resultado.erros,
        "avisos": resultado.avisos,
        "arquivos": arquivos,
        "total_partes": len(arquivos),
        "limite_kb": LIMITE_SEI_BYTES // BYTES_POR_KB,
        # Com a opção desligada, a interface usa a contagem para oferecer a troca
        "citacoes_por_recuo": resultado.citacoes_por_recuo,
        # O início de cada um, para quem decide ver o que muda antes de converter
        "citacoes_trechos": resultado.citacoes_trechos,
        # O que vem antes do item 1, omitido ou não: a interface oferece a troca
        "cabecalho_paragrafos": len(resultado.cabecalho_trechos),
        "cabecalho_trechos": resultado.cabecalho_trechos,
    }


def converter_memoria_json(
    nome_arquivo: str,
    conteudo_bytes: bytes,
    so_corpo: bool = False,
    forcar_unico: bool = False,
    forcar_partes: bool = False,
    max_kb: int = MAX_KB_PADRAO,
    max_nivel: int = 4,
    validar: bool = True,
    citacao_por_recuo: bool = False,
    omitir_cabecalho: bool = False,
    texto_reconhecido: str | None = None,
) -> str:
    """Converte bytes em memória e retorna uma string JSON (fácil de consumir no JS)."""
    res = converter_documento_memoria(
        nome_arquivo=nome_arquivo,
        conteudo_bytes=conteudo_bytes,
        so_corpo=so_corpo,
        forcar_unico=forcar_unico,
        forcar_partes=forcar_partes,
        max_kb=max_kb,
        max_nivel=max_nivel,
        validar=validar,
        citacao_por_recuo=citacao_por_recuo,
        omitir_cabecalho=omitir_cabecalho,
        texto_reconhecido=texto_reconhecido,
    )
    return json.dumps(res, ensure_ascii=False)
