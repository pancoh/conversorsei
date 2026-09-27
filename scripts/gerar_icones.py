"""
gerar_icones.py — Desenha os ícones PNG da PWA sem dependência externa.

O ícone é um documento branco sobre fundo azul institucional, com linhas de texto e um
canto dobrado. O PNG é escrito à mão (zlib e struct da biblioteca padrão) para que o
projeto não precise do Pillow só por causa de duas imagens.

Uso: python scripts/gerar_icones.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "icons"

AZUL = (37, 99, 235)
AZUL_ESCURO = (29, 78, 216)
BRANCO = (255, 255, 255)
CINZA = (203, 213, 225)

Cor = tuple[int, int, int]
Tela = list[list[Cor]]


def nova_tela(lado: int, cor: Cor) -> Tela:
    return [[cor for _ in range(lado)] for _ in range(lado)]


def retangulo(tela: Tela, x0: int, y0: int, x1: int, y1: int, cor: Cor, raio: int = 0) -> None:
    """Preenche um retângulo, opcionalmente com cantos arredondados."""
    lado = len(tela)
    for y in range(max(y0, 0), min(y1, lado)):
        for x in range(max(x0, 0), min(x1, lado)):
            if raio:
                # Fora do quarto de círculo do canto: deixa o pixel como está
                cx = x0 + raio if x < x0 + raio else (x1 - 1 - raio if x > x1 - 1 - raio else x)
                cy = y0 + raio if y < y0 + raio else (y1 - 1 - raio if y > y1 - 1 - raio else y)
                if (x - cx) ** 2 + (y - cy) ** 2 > raio * raio:
                    continue
            tela[y][x] = cor


def triangulo_canto(tela: Tela, x0: int, y0: int, tamanho: int, cor: Cor) -> None:
    """Dobra do canto superior direito da folha."""
    for i in range(tamanho):
        for x in range(x0 + i, x0 + tamanho):
            if 0 <= y0 + i < len(tela) and 0 <= x < len(tela):
                tela[y0 + i][x] = cor


def desenhar(lado: int) -> Tela:
    tela = nova_tela(lado, AZUL)
    u = lado / 16  # unidade de grade, para o desenho escalar com o tamanho

    def n(v: float) -> int:
        return int(round(v * u))

    # Folha de papel
    retangulo(tela, n(3.5), n(2.5), n(12.5), n(13.5), BRANCO, raio=n(0.6))
    # Canto dobrado
    triangulo_canto(tela, n(10.2), n(2.5), n(2.3), AZUL_ESCURO)

    # Linhas de texto: a primeira é o título, em azul e mais grossa
    retangulo(tela, n(5), n(5), n(11), n(5.9), AZUL, raio=n(0.2))
    for i in range(4):
        topo = 7.0 + i * 1.5
        largura = 11 if i % 2 == 0 else 9.5
        retangulo(tela, n(5), n(topo), n(largura), n(topo + 0.7), CINZA, raio=n(0.15))

    return tela


def escrever_png(tela: Tela, destino: Path) -> None:
    """Grava a tela como PNG truecolor sem compressão de filtro."""
    lado = len(tela)
    linhas = bytearray()
    for linha in tela:
        linhas.append(0)  # filtro "none" para cada scanline
        for r, g, b in linha:
            linhas.extend((r, g, b))

    def chunk(tipo: bytes, dados: bytes) -> bytes:
        bloco = tipo + dados
        return struct.pack(">I", len(dados)) + bloco + struct.pack(">I", zlib.crc32(bloco))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(linhas), 9))
    png += chunk(b"IEND", b"")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(png)


def main() -> None:
    for lado in (192, 512):
        caminho = DESTINO / f"icon-{lado}.png"
        escrever_png(desenhar(lado), caminho)
        print(f"{caminho.relative_to(RAIZ)} ({caminho.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
