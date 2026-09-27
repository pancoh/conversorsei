"""Gera o QR Code do Pix de apoio ao projeto (docs/pix.svg) e o código copia e cola.

O QR Code é estático: a chave, o recebedor e a cidade não mudam, e o valor fica em aberto
para quem paga. Por isso ele é gerado aqui, uma vez, e não no navegador, que precisaria de
uma biblioteca de QR Code só para isso.

O código segue o BR Code do Banco Central (EMV, com CRC16-CCITT no fim). O mesmo código
fica em PIX_COPIA_E_COLA, em docs/app.js, para o botão de copiar: tests/test_pix.py confere
que os dois batem com os dados daqui.

Uso:
    uv run python scripts/gerar_pix.py              # regrava docs/pix.svg e mostra o código
    uv run python scripts/gerar_pix.py --verificar  # só confere
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SVG = RAIZ / "docs" / "pix.svg"
APP_JS = RAIZ / "docs" / "app.js"

CHAVE = "conversorsei@gmail.com"
# O app do banco mostra o nome do titular da chave antes de confirmar; este é informativo.
# Sem acento e em caixa alta: alguns aplicativos rejeitam outros caracteres nesses campos
NOME = "CONVERSOR SEI"
CIDADE = "BRASILIA"


def campo(identificador: str, valor: str) -> str:
    """Campo EMV: identificador, tamanho com dois dígitos e valor."""
    return f"{identificador}{len(valor):02d}{valor}"


def crc16(dados: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, início 0xFFFF), exigido no fim do BR Code."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def payload_pix(chave: str = CHAVE, nome: str = NOME, cidade: str = CIDADE) -> str:
    """BR Code estático, sem valor definido: quem paga escolhe o valor."""
    if len(nome) > 25 or len(cidade) > 15:
        raise ValueError("O nome vai até 25 caracteres e a cidade até 15.")
    conta = campo("00", "br.gov.bcb.pix") + campo("01", chave)
    sem_crc = (
        campo("00", "01")
        + campo("26", conta)
        + campo("52", "0000")
        + campo("53", "986")
        + campo("58", "BR")
        + campo("59", nome)
        + campo("60", cidade)
        + campo("62", campo("05", "***"))
        + "6304"
    )
    return sem_crc + crc16(sem_crc)


def svg_do_qrcode(payload: str) -> str:
    """SVG do QR Code, determinístico: o mesmo código gera sempre o mesmo arquivo."""
    import segno

    qr = segno.make(payload, error="m", micro=False)
    saida = io.BytesIO()
    # Sem tamanho fixo e com viewBox, a imagem acompanha a largura da página. O fundo branco
    # mantém a margem de leitura no modo escuro. A margem de 4 módulos é o mínimo da norma
    qr.save(
        saida, kind="svg", border=4, xmldecl=False, omitsize=True, light="#fff", title="QR Code do Pix"
    )
    return saida.getvalue().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verificar", action="store_true", help="Só confere o SVG e o app.js.")
    args = parser.parse_args(argv)

    payload = payload_pix()
    svg = svg_do_qrcode(payload)
    if args.verificar:
        problemas = []
        if not SVG.is_file() or SVG.read_text(encoding="utf-8") != svg:
            problemas.append("docs/pix.svg não corresponde aos dados do Pix")
        if f"'{payload}'" not in APP_JS.read_text(encoding="utf-8"):
            problemas.append("PIX_COPIA_E_COLA em docs/app.js não corresponde aos dados do Pix")
        for problema in problemas:
            print(f"ERRO: {problema}. Rode 'uv run python scripts/gerar_pix.py'.", file=sys.stderr)
        return 1 if problemas else 0

    SVG.write_text(svg, encoding="utf-8")
    print(f"Gravado {SVG.relative_to(RAIZ)}.")
    print(f"Código copia e cola (PIX_COPIA_E_COLA em docs/app.js):\n{payload}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
