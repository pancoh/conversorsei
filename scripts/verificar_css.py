"""
verificar_css.py — Confere se o CSS compilado do Tailwind cobre as classes usadas na interface.

O CSS de docs/estilos.css é gerado pelo Tailwind CLI e versionado. Sem verificação, uma
classe nova em index.html ou app.js passaria despercebida e o estilo sumiria em produção.

A conferência é por classe, e não por bytes: a saída do Tailwind varia conforme a versão
do browserslist do ambiente, o que tornaria uma comparação byte a byte instável no CI.

Uso:
    python scripts/verificar_css.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSS = ROOT / "docs" / "estilos.css"
FONTES = [ROOT / "docs" / "index.html", ROOT / "docs" / "app.js"]

# Classes que não vêm do Tailwind: apenas ganchos usados pelo JS para achar elementos
PREFIXOS_PROPRIOS = ("btn-", "rotulo-")

RE_ATRIBUTO_CLASSE = re.compile(r'class(?:Name)?\s*=\s*["\'`]([^"\'`]+)["\'`]')
RE_STYLE_INLINE = re.compile(r"<style>(.*?)</style>", re.DOTALL)
# Comentários saem antes da busca: um nome de arquivo citado neles ("app.js ") viraria
# classe própria e deixaria de ser conferido no CSS compilado
RE_COMENTARIO_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)
# O nome da classe termina onde o seletor continua: "{", ",", combinador (" > *"), ":" etc.
RE_SELETOR_PROPRIO = re.compile(r"\.([A-Za-z][\w-]*)(?=[\s{,>+~:.\[])")


def classes_proprias() -> set[str]:
    """Classes definidas no <style> do próprio index.html, que não precisam estar no Tailwind."""
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    proprias: set[str] = set()
    for bloco in RE_STYLE_INLINE.findall(html):
        proprias |= set(RE_SELETOR_PROPRIO.findall(RE_COMENTARIO_CSS.sub("", bloco)))
    return proprias


def classes_usadas() -> set[str]:
    usadas: set[str] = set()
    for arquivo in FONTES:
        texto = arquivo.read_text(encoding="utf-8")
        for bloco in RE_ATRIBUTO_CLASSE.findall(texto):
            usadas |= {c for c in bloco.split() if c and "${" not in c}
    return usadas


def presente_no_css(classe: str, css: str) -> bool:
    """O Tailwind escapa . : / [ ] ao gerar o seletor, então a busca precisa escapar também."""
    padrao = "".join("\\\\" + re.escape(ch) if ch in ".:/[]" else re.escape(ch) for ch in classe)
    return re.search(rf"\.{padrao}(?![\w-])", css) is not None


def main() -> int:
    if not CSS.is_file():
        print(f"ERRO: {CSS} não existe. Gere com o comando descrito no README.", file=sys.stderr)
        return 1

    css = CSS.read_text(encoding="utf-8")
    ignoradas = classes_proprias()
    faltando = sorted(
        c
        for c in classes_usadas()
        if c not in ignoradas
        and not c.startswith(PREFIXOS_PROPRIOS)
        and not presente_no_css(c, css)
    )

    if faltando:
        print(
            "ERRO: classes sem regra no CSS compilado:\n  "
            + "\n  ".join(faltando)
            + "\n\nRecompile com:\n"
            "  npx tailwindcss@3.4.16 -c tailwind.config.js -i tailwind-input.css "
            "-o docs/estilos.css --minify",
            file=sys.stderr,
        )
        return 1

    print(f"CSS compilado cobre as {len(classes_usadas() - ignoradas)} classes usadas na interface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
