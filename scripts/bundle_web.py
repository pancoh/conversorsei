"""
bundle_web.py — Empacota o diretório conversorsei em um arquivo ZIP dentro de docs/
para ser consumido diretamente pelo Pyodide (WebAssembly) no GitHub Pages.

O ZIP é determinístico: o mesmo conteúdo sempre gera os mesmos bytes, o que permite
verificar no CI se a versão publicada está sincronizada com o código-fonte
(`python scripts/bundle_web.py --verificar`).

O script também grava no docs/index.html a marca de versão do app.js e do estilos.css
("app.js?v=<hash>"). Sem ela, o endereço dos dois não mudava entre deploys, e o cache do
GitHub Pages ou do navegador chegou a entregar o HTML novo com o app.js antigo, que
quebrava ao procurar um elemento que já não existia.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC_DIR = ROOT / "conversorsei"
DEST_ZIP = ROOT / "docs" / "conversorsei.zip"
INDEX = ROOT / "docs" / "index.html"
# Arquivos da página que o index.html chama com marca de versão
ARQUIVOS_COM_VERSAO = ("app.js", "estilos.css")

# Data fixa: sem isso o mtime do checkout entraria nos bytes do ZIP
DATA_FIXA = (1980, 1, 1, 0, 0, 0)
SUFIXOS_IGNORADOS = {".pyc", ".pyo"}
NOMES_IGNORADOS = {".DS_Store"}


def arquivos_do_pacote() -> list[Path]:
    """Lista, em ordem estável, os arquivos do pacote que entram no bundle."""
    return [
        p
        for p in sorted(SRC_DIR.rglob("*"))
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix not in SUFIXOS_IGNORADOS
        and p.name not in NOMES_IGNORADOS
    ]


def gerar_bytes_zip() -> tuple[bytes, list[str]]:
    """Gera o conteúdo do bundle em memória e a lista de arquivos incluídos."""
    buffer = io.BytesIO()
    incluidos: list[str] = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in arquivos_do_pacote():
            rel_path = file_path.relative_to(ROOT)
            info = zipfile.ZipInfo(str(rel_path), date_time=DATA_FIXA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, file_path.read_bytes())
            incluidos.append(str(rel_path))
    return buffer.getvalue(), incluidos


def criar_bundle(destino: Path = DEST_ZIP, silencioso: bool = False) -> Path:
    """Grava o bundle no destino informado."""
    conteudo, incluidos = gerar_bytes_zip()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)

    if not silencioso:
        print(f"Bundle gerado com sucesso em: {destino}")
        print(f"Tamanho: {len(conteudo) / 1024:.2f} KB")
        print(f"Total de arquivos empacotados: {len(incluidos)}")
        for f in incluidos:
            print(f"  - {f}")
    return destino


def verificar_bundle(destino: Path = DEST_ZIP) -> bool:
    """Confere se o bundle versionado corresponde ao código-fonte atual."""
    conteudo, _ = gerar_bytes_zip()
    if not destino.is_file():
        print(f"ERRO: {destino} não existe. Rode: python scripts/bundle_web.py", file=sys.stderr)
        return False
    if destino.read_bytes() != conteudo:
        print(
            f"ERRO: {destino} está defasado em relação a conversorsei/.\n"
            "Rode 'python scripts/bundle_web.py' e inclua o arquivo no commit.",
            file=sys.stderr,
        )
        return False
    print(f"Bundle {destino.name} está sincronizado com o código-fonte.")
    return True


def marca_de_versao(nome: str) -> str:
    """Primeiros caracteres do SHA-256 do arquivo: muda só quando o conteúdo muda."""
    return hashlib.sha256((ROOT / "docs" / nome).read_bytes()).hexdigest()[:10]


def index_com_versoes(html: str) -> str:
    """O index.html com a marca atual de cada arquivo de ARQUIVOS_COM_VERSAO."""
    for nome in ARQUIVOS_COM_VERSAO:
        padrao = re.compile(rf'"{re.escape(nome)}(\?v=[0-9a-f]*)?"')
        if not padrao.search(html):
            raise ValueError(f"index.html não chama {nome}; confira ARQUIVOS_COM_VERSAO")
        html = padrao.sub(f'"{nome}?v={marca_de_versao(nome)}"', html)
    return html


def gravar_versoes() -> None:
    html = INDEX.read_text(encoding="utf-8")
    novo = index_com_versoes(html)
    if novo != html:
        INDEX.write_text(novo, encoding="utf-8")
        print("Marcas de versão atualizadas em docs/index.html.")


def verificar_versoes() -> bool:
    """Confere se o index.html chama a versão atual do app.js e do estilos.css."""
    html = INDEX.read_text(encoding="utf-8")
    if index_com_versoes(html) != html:
        print(
            "ERRO: docs/index.html chama uma versão antiga de app.js ou estilos.css.\n"
            "Rode 'python scripts/bundle_web.py' e inclua o index.html no commit.",
            file=sys.stderr,
        )
        return False
    print("Marcas de versão de app.js e estilos.css estão atualizadas.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera (ou verifica) o bundle web do conversorsei.")
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Não grava nada: confere o ZIP e as marcas de versão do index.html.",
    )
    args = parser.parse_args(argv)

    if args.verificar:
        # As duas conferências rodam sempre, para o CI apontar tudo o que falta de uma vez
        bundle_ok = verificar_bundle()
        versoes_ok = verificar_versoes()
        return 0 if bundle_ok and versoes_ok else 1

    criar_bundle()
    gravar_versoes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
