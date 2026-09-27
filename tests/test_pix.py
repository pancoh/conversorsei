"""O Pix de apoio: o QR Code e o código copia e cola da página precisam ser o mesmo Pix.

Um código com CRC errado é recusado pelo aplicativo do banco, e um QR Code que não bate com
o código copiado mandaria o dinheiro para outro lugar. Os dois saem de scripts/gerar_pix.py.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gerar_pix", RAIZ / "scripts" / "gerar_pix.py")
assert _spec and _spec.loader
gerar_pix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gerar_pix)


def test_crc16_segue_o_ccitt_do_br_code():
    # Valor de referência do CRC16-CCITT (0x1021, início 0xFFFF)
    assert gerar_pix.crc16("123456789") == "29B1"


def test_codigo_pix_tem_a_estrutura_do_br_code():
    payload = gerar_pix.payload_pix()
    assert payload.startswith("000201")
    assert "0014br.gov.bcb.pix" in payload
    assert f"01{len(gerar_pix.CHAVE):02d}{gerar_pix.CHAVE}" in payload
    assert "5303986" in payload and "5802BR" in payload
    # O CRC fecha o código e confere com o resto dele
    assert re.fullmatch(r".*6304[0-9A-F]{4}", payload)
    assert gerar_pix.crc16(payload[:-4]) == payload[-4:]


def test_qrcode_e_codigo_da_pagina_batem_com_os_dados_do_pix():
    """docs/pix.svg e PIX_COPIA_E_COLA em docs/app.js saem dos mesmos dados."""
    assert gerar_pix.main(["--verificar"]) == 0
    app = (RAIZ / "docs" / "app.js").read_text(encoding="utf-8")
    assert f"const PIX_CHAVE = '{gerar_pix.CHAVE}';" in app
