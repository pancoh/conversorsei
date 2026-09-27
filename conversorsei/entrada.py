"""
entrada.py — Normaliza a origem de um documento: caminho em disco ou conteúdo em memória.

A interface web recebe os bytes do arquivo direto do navegador. Sem isto, cada conversão
teria de gravar a entrada num arquivo temporário só para o leitor abrir em seguida, o que
pesa no sistema de arquivos emulado do WebAssembly.
"""
from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

# O que os leitores de documento aceitam como origem
FonteDocumento = str | Path | bytes | bytearray | IO[bytes]


class StreamNomeado(io.BytesIO):
    """Conteúdo em memória que carrega o nome do arquivo de origem.

    Os leitores citam o nome nas mensagens de erro. Sem ele, quem envia 'contrato.odt'
    pela web leria um genérico 'documento.odt' no lugar do próprio arquivo.
    """

    def __init__(self, conteudo: bytes | bytearray, nome: str) -> None:
        super().__init__(bytes(conteudo))
        self.name = nome


def nome_da_fonte(fonte: FonteDocumento, nome_padrao: str = "documento") -> str:
    """Nome do documento, para compor as mensagens de erro."""
    if isinstance(fonte, (str, Path)):
        return Path(fonte).name
    if isinstance(fonte, (bytes, bytearray)):
        return nome_padrao
    return Path(getattr(fonte, "name", nome_padrao) or nome_padrao).name


@contextmanager
def abrir_binario(fonte: FonteDocumento, nome_padrao: str = "documento") -> Iterator[IO[bytes]]:
    """Entrega a fonte como stream binário, fechando só o que foi aberto aqui.

    Um stream recebido de fora continua sob responsabilidade de quem o abriu, e é
    reposicionado no início para que uma segunda leitura não devolva vazio.
    """
    if isinstance(fonte, (str, Path)):
        arquivo = Path(fonte).open("rb")
        try:
            yield arquivo
        finally:
            arquivo.close()
        return

    if isinstance(fonte, (bytes, bytearray)):
        yield io.BytesIO(bytes(fonte))
        return

    if not hasattr(fonte, "read"):
        # Sem esta guarda o objeto seguiria adiante e estouraria lá dentro do leitor,
        # com uma mensagem que não diz de onde veio o problema
        raise TypeError(
            f"Fonte de documento inválida: {type(fonte).__name__}. "
            "Use um caminho, bytes ou um stream binário."
        )

    try:
        fonte.seek(0)
    except (AttributeError, OSError, ValueError):
        # Stream sem posicionamento (um pipe, por exemplo) é lido de onde estiver
        pass
    yield fonte


def ler_bytes(fonte: FonteDocumento) -> bytes:
    """Conteúdo completo da fonte."""
    with abrir_binario(fonte) as binario:
        return binario.read()
