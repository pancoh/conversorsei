"""Guarda a fronteira entre o código versionado e os documentos de trabalho."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
# 'dados' cobre as subpastas entrada/ e saida/ e também arquivo solto na raiz dela.
# 'entrada' e 'saida' cobrem o fallback da CLI quando dados/entrada/ não existe.
PASTAS_DE_TRABALHO = ("dados", "entrada", "saida")


def arquivos_versionados(caminho: str) -> list[str]:
    """Lista o que o git rastreia sob o caminho, ou pula o teste fora de um repositório."""
    if not (RAIZ / ".git").exists():
        pytest.skip("Fora de um repositório git (instalação a partir do pacote).")
    try:
        resultado = subprocess.run(
            # quotePath=false e -z preservam acento no nome, para que o caminho da
            # mensagem de falha possa ser copiado direto no 'git rm --cached'.
            ["git", "-c", "core.quotePath=false", "ls-files", "-z", "--", caminho],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("git não está disponível no PATH.")
    return [linha for linha in resultado.stdout.split("\0") if linha.strip()]


@pytest.mark.parametrize("pasta", PASTAS_DE_TRABALHO)
def test_documento_de_trabalho_nao_e_versionado(pasta):
    """Documento institucional não entra no repositório, nem por engano.

    O .gitignore não basta: ele não alcança arquivo já rastreado nem `git add -f`.
    Foi assim que um despacho ficou versionado desde o commit inicial. Se este teste
    falhar, tire o arquivo do índice com `git rm --cached <arquivo>` (ele continua
    no disco) antes de seguir.
    """
    intrusos = [a for a in arquivos_versionados(pasta) if Path(a).name != ".gitkeep"]
    assert intrusos == [], (
        f"Documento de trabalho versionado em {pasta}/: {intrusos}. "
        "Rode 'git rm --cached <arquivo>' para tirar do índice mantendo o arquivo no disco."
    )
