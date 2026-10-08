"""
cli.py — Interface de Linha de Comando (CLI) para conversão universal de documentos para o SEI.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from conversorsei.core import (
    EXTENSOES_RECONHECIDAS,
    EXTENSOES_SUPORTADAS,
    ResultadoConversao,
    converter_diretorio,
    converter_documento,
    entra_na_varredura,
)

INTERVALO_WATCH_PADRAO = 2.0


def pasta_de_destino(caminho: Path, alvos: list[str], outdir: Path | None) -> Path | None:
    """O watch conserva as subpastas, como a conversão de diretório."""
    if outdir is None:
        return None
    for alvo in alvos:
        raiz = Path(alvo)
        if raiz.is_dir() and caminho.is_relative_to(raiz):
            return outdir / caminho.parent.relative_to(raiz)
    return outdir


def arquivos_observaveis(alvos: list[str], recursivo: bool) -> dict[Path, tuple[int, int]]:
    """Mapeia cada arquivo suportado sob os alvos para a sua marca de modificação."""
    estado: dict[Path, tuple[int, int]] = {}
    for alvo_str in alvos:
        p_alvo = Path(alvo_str)
        # Formato retirado entra: a conversão falha com a orientação, e o watch a mostra
        if p_alvo.is_file():
            candidatos = [p_alvo] if p_alvo.suffix.lower() in EXTENSOES_RECONHECIDAS else []
        elif p_alvo.is_dir():
            candidatos = [f for f in p_alvo.glob("**/*" if recursivo else "*") if entra_na_varredura(f)]
        else:
            continue
        for f in candidatos:
            if not f.is_file():
                continue
            try:
                st = f.stat()
            except OSError:
                # O arquivo pode sumir entre o glob e o stat; a varredura seguinte resolve
                continue
            estado[f] = (st.st_mtime_ns, st.st_size)
    return estado


def ciclo_de_observacao(
    alvos: list[str],
    recursivo: bool,
    convertidos: dict[Path, tuple[int, int]],
    pendentes: dict[Path, tuple[int, int]],
) -> list[Path]:
    """Uma varredura: devolve os arquivos prontos para converter e atualiza o controle.

    Um arquivo só entra na lista quando aparece igual em duas varreduras seguidas. O
    Word e o editor gravam em etapas, e converter no meio da gravação leria um arquivo
    truncado. O preço é um intervalo de espera antes da primeira conversão.
    """
    atual = arquivos_observaveis(alvos, recursivo)
    prontos: list[Path] = []

    for caminho, marca in atual.items():
        if convertidos.get(caminho) == marca:
            continue
        if pendentes.get(caminho) != marca:
            pendentes[caminho] = marca
            continue
        pendentes.pop(caminho, None)
        convertidos[caminho] = marca
        prontos.append(caminho)

    for caminho in list(convertidos):
        if caminho not in atual:
            del convertidos[caminho]
    for caminho in list(pendentes):
        if caminho not in atual:
            del pendentes[caminho]

    return sorted(prontos)


def aviso_de_citacao(res: ResultadoConversao, aplicada: bool) -> str | None:
    """Explica o que aconteceu com os parágrafos com forma de citação, se houver algum.

    Desligada a opção, diz como ligá-la: a regra adivinha pela medida e erra em alguns
    documentos, então quem converte decide, como faz o botão da interface web.
    """
    recuo, aspas = res.citacoes_por_recuo, res.citacoes_entre_aspas
    n = recuo + aspas
    if not n:
        return None
    um = n == 1
    paragrafos = "1 parágrafo" if um else f"{n} parágrafos"
    if not aspas:
        sujeito = f"{paragrafos} {'recuado' if um else 'recuados'} e em fonte menor que a do texto"
    elif not recuo:
        sujeito = f"{paragrafos} {'entre aspas' if um else 'em citações entre aspas'} com mais de uma linha"
    else:
        sujeito = f"{paragrafos} ({recuo} recuados e em fonte menor, {aspas} entre aspas)"
    if aplicada:
        return f"{sujeito} {'foi convertido' if um else 'foram convertidos'} como Citação."
    if um:
        return f"{sujeito} parece citação e saiu como texto comum. Para convertê-lo, use --citacao-por-recuo."
    return f"{sujeito} parecem citação e saíram como texto comum. Para convertê-los, use --citacao-por-recuo."


def aviso_de_cabecalho(res: ResultadoConversao, aplicada: bool) -> str | None:
    """Diz o que saiu da conversão com --sem-cabecalho, ou por que nada saiu.

    Sem a opção, fica calado: quase todo documento tem algo antes do item 1, e repetir
    isso a cada conversão só encheria o relatório.
    """
    if not aplicada:
        return None
    n = len(res.cabecalho_trechos)
    if not n:
        return "Nenhum parágrafo foi omitido: o documento não tem item 1 depois de um cabeçalho."
    if n == 1:
        return "1 parágrafo antes do item 1 foi omitido."
    return f"{n} parágrafos antes do item 1 foram omitidos."


def observar(args: argparse.Namespace, alvos: list[str], outdir: Path | None, validar: bool) -> int:
    """Converte a cada arquivo novo ou alterado, até o Ctrl+C.

    Todo print sai com flush: em processo longo com a saída redirecionada ou em pipe,
    o buffer só seria esvaziado no fim e o acompanhamento ficaria mudo.
    """
    print(f"Observando {', '.join(alvos)} a cada {args.intervalo:g}s. Ctrl+C encerra.", flush=True)
    convertidos: dict[Path, tuple[int, int]] = {}
    pendentes: dict[Path, tuple[int, int]] = {}
    destinos_reservados: dict[Path, Path] = {}

    try:
        while True:
            # O nome de saída de um arquivo apagado ou renomeado fica livre: sem isto, um
            # a.txt criado depois de apagar o a.md seria recusado até reiniciar o watch
            for destino, origem in list(destinos_reservados.items()):
                if not origem.exists():
                    del destinos_reservados[destino]
            for caminho in ciclo_de_observacao(alvos, args.recursivo, convertidos, pendentes):
                res = converter_documento(
                    caminho_entrada=caminho,
                    outdir=pasta_de_destino(caminho, alvos, outdir),
                    so_corpo=args.corpo,
                    max_nivel=args.max_nivel,
                    validar=validar,
                    citacao_por_recuo=args.citacao_por_recuo,
                    omitir_cabecalho=args.sem_cabecalho,
                    destinos_reservados=destinos_reservados,
                )
                hora = datetime.now().strftime("%H:%M:%S")
                if res.sucesso:
                    destinos = ", ".join(g.name for g in res.arquivos_gerados)
                    print(f"[{hora}] OK   {caminho.name} -> {destinos}", flush=True)
                    for aviso in res.avisos:
                        print(f"[{hora}]      aviso: {aviso}", flush=True)
                    citacao = aviso_de_citacao(res, args.citacao_por_recuo)
                    if citacao:
                        print(f"[{hora}]      citação: {citacao}", flush=True)
                    cabecalho = aviso_de_cabecalho(res, args.sem_cabecalho)
                    if cabecalho:
                        print(f"[{hora}]      cabeçalho: {cabecalho}", flush=True)
                else:
                    print(f"[{hora}] FALHA {caminho.name}", file=sys.stderr, flush=True)
                    for err in res.erros:
                        print(f"[{hora}]      erro: {err}", file=sys.stderr, flush=True)
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nObservação encerrada.", flush=True)
        return 0


def nivel_maximo(valor: str) -> int:
    """O SEI só tem Item_Nivel1 a Item_Nivel4: fora disso, a classe gerada não existiria."""
    try:
        nivel = int(valor)
    except ValueError:
        nivel = 0
    if not 1 <= nivel <= 4:
        raise argparse.ArgumentTypeError(f"use um número de 1 a 4 (recebido: {valor})")
    return nivel


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conversorsei",
        description="Converte arquivos DOCX, PDF, ODT, HTML, MD e TXT em HTML no padrão institucional do editor SEI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  conversorsei documento.docx
  conversorsei minuta.md -o ./saida_sei/
  conversorsei ./pasta_de_documentos/ -r -o ./saida/
  conversorsei doc.docx --corpo  # só os parágrafos, sem <head> nem <style>
  conversorsei -w                # observa dados/entrada/ e converte a cada alteração
""",
    )

    parser.add_argument(
        "alvos",
        nargs="*",
        default=[],
        help="Arquivos ou diretórios a converter (.docx, .pdf, .odt, .html, .md, .txt). Se omitido, processa dados/entrada/.",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=None,
        help=(
            "Diretório de destino dos arquivos HTML gerados. Sem ele, a saída vai para a pasta de cada "
            "entrada; sem alvo, para dados/saida/ (ou saida/, quando a pasta lida é entrada/)."
        ),
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Nome explícito do arquivo de saída. Só vale com um único arquivo de entrada.",
    )
    parser.add_argument(
        "--corpo",
        action="store_true",
        help="Gera apenas o fragmento HTML do corpo (sem <head>/<style>).",
    )
    parser.add_argument(
        "--max-nivel",
        type=nivel_maximo,
        default=4,
        help=(
            "Profundidade máxima do item numerado digitado no texto ('1.1.1.'), de 1 a 4 (padrão: 4). "
            "Os níveis mais profundos viram alíneas. Títulos e listas do Word mantêm o nível que têm."
        ),
    )
    parser.add_argument(
        "-r",
        "--recursivo",
        action="store_true",
        help="Varre subdiretórios recursivamente quando uma pasta for informada.",
    )
    parser.add_argument(
        "--citacao-por-recuo",
        action="store_true",
        help=(
            "Converte como Citação o parágrafo recuado (2 cm ou mais) e em fonte menor que a do texto (.docx e "
            ".odt) e os parágrafos de uma citação entre aspas com mais de uma linha (todos os formatos)."
        ),
    )
    parser.add_argument(
        "--sem-cabecalho",
        action="store_true",
        help="Começa a saída no item 1 e omite o que vem antes (título, número, processo), que o SEI já gera.",
    )
    parser.add_argument(
        "--no-validar",
        action="store_true",
        help="Desativa a validação das regras institucionais.",
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="Fica em execução convertendo cada arquivo novo ou alterado no alvo (Ctrl+C encerra).",
    )
    parser.add_argument(
        "--intervalo",
        type=float,
        default=INTERVALO_WATCH_PADRAO,
        help=f"Segundos entre as varreduras do modo --watch (padrão: {INTERVALO_WATCH_PADRAO}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exibe o relatório de conversão em formato JSON.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = criar_parser()
    args = parser.parse_args(argv)

    alvos: list[str] = args.alvos
    outdir: Path | None = args.outdir
    validar: bool = not args.no_validar

    # Modo padrão: se nenhum alvo for passado, procura dados/entrada/ ou entrada/
    if not alvos:
        candidatos = [Path("dados/entrada"), Path("entrada")]
        pasta_padrao = next((p for p in candidatos if p.is_dir()), None)
        if pasta_padrao:
            alvos = [str(pasta_padrao)]
            if outdir is None:
                outdir = Path("dados/saida") if pasta_padrao == Path("dados/entrada") else Path("saida")
            args.recursivo = True
        else:
            parser.print_help()
            print("\nAVISO: nenhum arquivo especificado e pasta padrão 'dados/entrada/' não encontrada.", file=sys.stderr)
            return 1

    if args.watch:
        if args.saida:
            print("ERRO: --saida define um nome fixo e não combina com --watch.", file=sys.stderr)
            return 1
        return observar(args, alvos, outdir, validar)

    um_arquivo = len(alvos) == 1 and Path(alvos[0]).is_file()
    if args.saida and not um_arquivo:
        # Antes, a opção era ignorada em silêncio, e a saída saía com o nome padrão
        print("ERRO: --saida define o nome de um arquivo só e vale apenas com um arquivo de entrada.", file=sys.stderr)
        return 1

    resultados = []
    total_erros = 0
    destinos_reservados: dict[Path, Path] = {}

    if um_arquivo and args.saida:
        res = converter_documento(
            caminho_entrada=alvos[0],
            caminho_saida=args.saida,
            so_corpo=args.corpo,
            max_nivel=args.max_nivel,
            validar=validar,
            citacao_por_recuo=args.citacao_por_recuo,
            omitir_cabecalho=args.sem_cabecalho,
        )
        resultados.append(res)
    else:
        for alvo_str in alvos:
            p_alvo = Path(alvo_str)
            if not p_alvo.exists():
                print(f"ERRO: alvo não encontrado: {p_alvo}", file=sys.stderr)
                total_erros += 1
                continue

            if p_alvo.is_dir():
                res_dir = converter_diretorio(
                    diretorio=p_alvo,
                    outdir=outdir,
                    recursivo=args.recursivo,
                    so_corpo=args.corpo,
                    max_nivel=args.max_nivel,
                    validar=validar,
                    citacao_por_recuo=args.citacao_por_recuo,
                    omitir_cabecalho=args.sem_cabecalho,
                    destinos_reservados=destinos_reservados,
                )
                resultados.extend(res_dir)
            elif p_alvo.is_file():
                # Formato retirado segue para a conversão, que falha com a orientação
                if p_alvo.suffix.lower() not in EXTENSOES_RECONHECIDAS:
                    print(
                        f"AVISO: ignorando formato não suportado: {p_alvo.name} "
                        f"(aceitos: {', '.join(sorted(EXTENSOES_SUPORTADAS))})",
                        file=sys.stderr,
                    )
                    continue
                res = converter_documento(
                    caminho_entrada=p_alvo,
                    outdir=outdir,
                    so_corpo=args.corpo,
                    max_nivel=args.max_nivel,
                    validar=validar,
                    citacao_por_recuo=args.citacao_por_recuo,
                    omitir_cabecalho=args.sem_cabecalho,
                    destinos_reservados=destinos_reservados,
                )
                resultados.append(res)

    if args.json:
        payload = [
            {
                "origem": str(r.arquivo_origem),
                "sucesso": r.sucesso,
                "gerados": [str(g) for g in r.arquivos_gerados],
                "erros": r.erros,
                "avisos": r.avisos,
                "citacoes_por_recuo": r.citacoes_por_recuo,
                "citacoes_entre_aspas": r.citacoes_entre_aspas,
                # Os mesmos campos que a interface web recebe
                "citacoes_trechos": r.citacoes_trechos,
                "cabecalho_paragrafos": len(r.cabecalho_trechos),
                "cabecalho_trechos": r.cabecalho_trechos,
            }
            for r in resultados
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if any(not r.sucesso for r in resultados) or total_erros > 0 else 0

    # Saída amigável no terminal
    if not resultados and total_erros == 0:
        print("Nenhum arquivo compatível encontrado para conversão.")
        return 1

    print("=" * 60)
    print("RELATÓRIO DE CONVERSÃO PARA O SEI")
    print("=" * 60)

    sucessos = 0
    for r in resultados:
        if r.sucesso:
            sucessos += 1
            print(f"OK   {r.arquivo_origem.name} -> {r.arquivos_gerados[0]}")
            for aviso in r.avisos:
                print(f"     aviso: {aviso}")
            citacao = aviso_de_citacao(r, args.citacao_por_recuo)
            if citacao:
                print(f"     citação: {citacao}")
            cabecalho = aviso_de_cabecalho(r, args.sem_cabecalho)
            if cabecalho:
                print(f"     cabeçalho: {cabecalho}")
        else:
            total_erros += 1
            print(f"FALHA {r.arquivo_origem.name}:")
            for err in r.erros:
                print(f"     erro: {err}")

    print("-" * 60)
    print(f"Total processados: {len(resultados)} | Sucessos: {sucessos} | Falhas: {total_erros}")
    print("=" * 60)

    return 1 if total_erros > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
