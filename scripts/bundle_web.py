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

Grava ainda, a partir do CHANGELOG.md, a versão do rodapé e o quadro Novidades. O
histórico vai dentro do index.html, e não num arquivo à parte, para abrir sem rede sem
mexer na lista do service worker. Com --notas, imprime o texto de uma versão para a
Release do GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import tomllib
import zipfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC_DIR = ROOT / "conversorsei"
DEST_ZIP = ROOT / "docs" / "conversorsei.zip"
INDEX = ROOT / "docs" / "index.html"
# Arquivos da página que o index.html chama com marca de versão
ARQUIVOS_COM_VERSAO = ("app.js", "estilos.css")
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"

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


def index_atualizado(html: str) -> str:
    """O index.html com as marcas dos arquivos, a versão do rodapé e o quadro Novidades."""
    return index_com_versoes(index_com_novidades(html))


def gravar_versoes() -> None:
    html = INDEX.read_text(encoding="utf-8")
    novo = index_atualizado(html)
    if novo != html:
        INDEX.write_text(novo, encoding="utf-8")
        print("Marcas de versão atualizadas em docs/index.html.")


def verificar_versoes() -> bool:
    """Confere se o index.html chama a versão atual do app.js e do estilos.css."""
    html = INDEX.read_text(encoding="utf-8")
    if index_atualizado(html) != html:
        print(
            "ERRO: docs/index.html chama uma versão antiga de app.js ou estilos.css, ou não traz a\n"
            "versão e o histórico atuais do CHANGELOG.md.\n"
            "Rode 'python scripts/bundle_web.py' e inclua o index.html no commit.",
            file=sys.stderr,
        )
        return False
    print("Marcas de versão de app.js e estilos.css, versão e histórico estão atualizados.")
    return True


# Histórico de versões (CHANGELOG.md). Cada versão abre com "## 0.5.0 (2026-10-07)"; as
# mudanças ainda sem número ficam em "## Em desenvolvimento"
EM_DESENVOLVIMENTO = "Em desenvolvimento"
RE_TITULO_VERSAO = re.compile(r"^## (\d+\.\d+\.\d+) \((\d{4})-(\d{2})-(\d{2})\)$")
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip
INICIO_NOVIDADES = "<!-- novidades:inicio -->"
FIM_NOVIDADES = "<!-- novidades:fim -->"
RE_VERSAO_RODAPE = re.compile(r'(<span id="versao-atual">)[^<]*(</span>)')


@dataclass
class Versao:
    """Uma seção do histórico. Sem número, é a das mudanças ainda não lançadas."""

    numero: str | None
    data: str | None = None
    # ("p", texto) para parágrafo e ("li", texto) para item, já sem a quebra de linha
    blocos: list[tuple[str, str]] = field(default_factory=list)


def ler_historico(texto: str) -> list[Versao]:
    """Lê as seções do CHANGELOG.md, na ordem do arquivo (a mais recente primeiro).

    Item começa com "- " e continua nas linhas recuadas; o resto é parágrafo. Linha em
    branco fecha o bloco. Título fora do padrão é erro, para não sumir uma versão inteira
    por um parêntese a menos.
    """
    versoes: list[Versao] = []
    bloco: list[str] = []
    tipo = "p"

    def fechar() -> None:
        if bloco and versoes:
            versoes[-1].blocos.append((tipo, " ".join(bloco)))
        bloco.clear()

    for linha in texto.splitlines():
        if linha.startswith("## "):
            fechar()
            titulo = linha[3:].strip()
            if titulo == EM_DESENVOLVIMENTO:
                versoes.append(Versao(None))
                continue
            m = RE_TITULO_VERSAO.match(linha)
            if not m:
                raise ValueError(f'Título de versão fora do padrão no CHANGELOG.md: "{linha}"')
            ano, mes, dia = int(m.group(2)), int(m.group(3)), int(m.group(4))
            versoes.append(Versao(m.group(1), f"{dia} de {MESES[mes - 1]} de {ano}"))
        elif not linha.strip():
            fechar()
        elif linha.startswith("- "):
            fechar()
            tipo = "li"
            bloco.append(linha[2:].strip())
        elif bloco and linha.startswith(" "):
            bloco.append(linha.strip())
        elif versoes:
            if tipo == "li":
                fechar()
            tipo = "p"
            bloco.append(linha.strip())
    fechar()
    return versoes


def versao_do_projeto() -> str:
    """A versão do pyproject.toml, que é a que vale para o pacote e para a página."""
    with PYPROJECT.open("rb") as arquivo:
        return str(tomllib.load(arquivo)["project"]["version"])


def ultima_versao(versoes: list[Versao]) -> Versao:
    """A versão lançada mais recente, que precisa ser a do pyproject.toml."""
    lancadas = [v for v in versoes if v.numero]
    if not lancadas:
        raise ValueError("O CHANGELOG.md não tem nenhuma versão lançada.")
    projeto = versao_do_projeto()
    if lancadas[0].numero != projeto:
        raise ValueError(
            f"O pyproject.toml está na versão {projeto}, e o CHANGELOG.md, na {lancadas[0].numero}. "
            "Ao lançar uma versão, mude os dois juntos."
        )
    return lancadas[0]


def _inline(texto: str) -> str:
    """Escapa o texto e traduz as marcas que o histórico usa: **negrito** e `código`."""
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(texto, quote=False))
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html)


def html_das_novidades(versoes: list[Versao]) -> str:
    """O histórico como HTML do quadro Novidades. A seção em desenvolvimento só entra com
    algum item: a página publicada já tem essas mudanças, ainda sem número."""
    secoes = []
    for versao in versoes:
        if not versao.blocos:
            continue
        if versao.numero:
            titulo = f'Versão {versao.numero} <span class="font-normal text-slate-500">{versao.data}</span>'
        else:
            titulo = f'{EM_DESENVOLVIMENTO} <span class="font-normal text-slate-500">já na página</span>'
        partes = [f'<h4 class="font-semibold text-slate-800">{titulo}</h4>']
        itens: list[str] = []
        for tipo, texto in versao.blocos:
            if tipo == "li":
                itens.append(f"<li>{_inline(texto)}</li>")
                continue
            if itens:
                partes.append(f'<ul class="list-disc pl-5 space-y-1.5">{"".join(itens)}</ul>')
                itens = []
            partes.append(f"<p>{_inline(texto)}</p>")
        if itens:
            partes.append(f'<ul class="list-disc pl-5 space-y-1.5">{"".join(itens)}</ul>')
        secoes.append('        <section class="space-y-2">\n          ' + "\n          ".join(partes) + "\n        </section>")
    return "\n".join(secoes)


def index_com_novidades(html: str) -> str:
    """O index.html com a versão do rodapé e o quadro Novidades tirados do CHANGELOG.md."""
    versoes = ler_historico(CHANGELOG.read_text(encoding="utf-8"))
    numero = ultima_versao(versoes).numero
    if not RE_VERSAO_RODAPE.search(html) or html.count(INICIO_NOVIDADES) != 1 or html.count(FIM_NOVIDADES) != 1:
        raise ValueError("index.html sem a versão do rodapé ou sem as marcas do quadro Novidades")
    html = RE_VERSAO_RODAPE.sub(rf"\g<1>{numero}\g<2>", html)
    inicio = html.index(INICIO_NOVIDADES) + len(INICIO_NOVIDADES)
    fim = html.index(FIM_NOVIDADES)
    return html[:inicio] + "\n" + html_das_novidades(versoes) + "\n        " + html[fim:]


def notas_da_versao(numero: str) -> str:
    """O texto de uma versão em Markdown, para a Release do GitHub.

    Cada bloco fica numa linha só: na Release, a quebra de linha do arquivo viraria
    quebra no texto exibido.
    """
    for versao in ler_historico(CHANGELOG.read_text(encoding="utf-8")):
        if versao.numero == numero:
            linhas: list[str] = []
            anterior = None
            for tipo, texto in versao.blocos:
                if linhas and not (tipo == anterior == "li"):
                    linhas.append("")
                linhas.append(f"- {texto}" if tipo == "li" else texto)
                anterior = tipo
            return "\n".join(linhas) + "\n"
    raise ValueError(f"A versão {numero} não está no CHANGELOG.md.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera (ou verifica) o bundle web do conversorsei.")
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Não grava nada: confere o ZIP e as marcas de versão do index.html.",
    )
    parser.add_argument(
        "--notas",
        metavar="VERSAO",
        help="Não grava nada: imprime o texto da versão no CHANGELOG.md, para a Release do GitHub.",
    )
    args = parser.parse_args(argv)

    if args.notas:
        print(notas_da_versao(args.notas), end="")
        return 0

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
