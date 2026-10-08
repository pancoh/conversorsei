"""Corpus de documentos reais: cada um é convertido e comparado com a saída revisada.

Os outros testes montam o documento no próprio código, com o caso que querem provar. Aqui
entra o documento como ele chega de fato (notas técnicas, ofícios, pareceres), com o que
o autor fez no Word ou no LibreOffice. Uma mudança no conversor que altere a saída de
qualquer um deles falha aqui, mesmo sem teste escrito para o caso.

Os documentos ficam em tests/corpus/documentos/ e precisam estar anonimizados (veja
tests/corpus/README.md). O exemplo de exemplos/ também entra.

Documento novo, ou mudança de saída intencional:

    ATUALIZAR_CORPUS=1 uv run pytest tests/test_corpus.py

grava a saída atual em tests/corpus/esperado/. Revise o diff antes do commit: o arquivo
esperado é a decisão de que aquela saída está certa.
"""
from __future__ import annotations

import difflib
import os
from pathlib import Path

import pytest

from conversorsei.core import EXTENSOES_SUPORTADAS, converter_bytes

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "tests" / "corpus"
ESPERADO = CORPUS / "esperado"
ATUALIZAR = os.environ.get("ATUALIZAR_CORPUS") == "1"
LINHAS_DO_DIFF = 80


def documentos() -> list[Path]:
    pastas = (CORPUS / "documentos", RAIZ / "exemplos")
    return sorted(
        arquivo
        for pasta in pastas
        if pasta.is_dir()
        for arquivo in pasta.iterdir()
        if arquivo.suffix.lower() in EXTENSOES_SUPORTADAS
    )


def saida_do_documento(arquivo: Path) -> str:
    """Corpo convertido, num arquivo só, com os avisos no topo como comentários.

    Só o corpo: o CSS muda por outros motivos e faria todo o corpus falhar a cada ajuste
    de estilo.
    """
    res = converter_bytes(arquivo.name, arquivo.read_bytes(), so_corpo=True)
    if not res.sucesso:
        return "".join(f"<!-- erro: {erro} -->\n" for erro in res.erros)
    avisos = "".join(f"<!-- aviso: {aviso} -->\n" for aviso in res.avisos)
    return avisos + "\n".join(arquivo_sei.conteudo for arquivo_sei in res.arquivos)


@pytest.mark.parametrize("arquivo", documentos(), ids=lambda arquivo: arquivo.name)
def test_documento_do_corpus_sai_como_revisado(arquivo: Path) -> None:
    esperado = ESPERADO / f"{arquivo.name}.html"
    atual = saida_do_documento(arquivo)

    if ATUALIZAR:
        ESPERADO.mkdir(parents=True, exist_ok=True)
        esperado.write_text(atual, encoding="utf-8")
        return

    assert esperado.is_file(), (
        f"{arquivo.name} não tem saída revisada. Rode ATUALIZAR_CORPUS=1 uv run pytest "
        f"tests/test_corpus.py e revise {esperado.relative_to(RAIZ)} antes do commit."
    )
    anterior = esperado.read_text(encoding="utf-8")
    if atual != anterior:
        diff = difflib.unified_diff(
            anterior.splitlines(), atual.splitlines(), "revisado", "atual", lineterm="", n=2
        )
        linhas = list(diff)
        corte = "\n..." if len(linhas) > LINHAS_DO_DIFF else ""
        pytest.fail(
            f"A saída de {arquivo.name} mudou. Se a mudança é intencional, rode "
            "ATUALIZAR_CORPUS=1 uv run pytest tests/test_corpus.py e revise o diff.\n"
            + "\n".join(linhas[:LINHAS_DO_DIFF])
            + corte,
            pytrace=False,
        )


def test_saida_revisada_sem_documento_e_apontada() -> None:
    """Um arquivo esperado sem o documento correspondente é resto de documento removido."""
    nomes = {f"{arquivo.name}.html" for arquivo in documentos()}
    orfaos = sorted(p.name for p in ESPERADO.glob("*.html") if p.name not in nomes)
    assert not orfaos, f"Saída revisada sem documento em tests/corpus/esperado/: {orfaos}"
