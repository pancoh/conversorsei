"""
montagem.py — Monta o HTML institucional de saída e decide o nome do arquivo gerado.
"""
from __future__ import annotations

from pathlib import Path

from conversorsei.recursos import obter_estilos_sei

# Título de todo HTML gerado. A varredura de pastas o procura para não converter de novo
# a própria saída, que agora é um formato de entrada
TITULO_DA_SAIDA = "Conteúdo formatado para o SEI"

# Contadores CSS usados pelas classes institucionais do SEI
NOMES_CONTADORES = (
    "item-n1",
    "item-n2",
    "item-n3",
    "item-n4",
    "paragrafo-n1",
    "paragrafo-n2",
    "paragrafo-n3",
    "romano_maiusculo",
    "letra_minuscula",
)
# Todos começam em zero: a numeração da prévia nasce no primeiro item do documento
COUNTER_RESET_INICIAL = " ".join(f"{nome} 0" for nome in NOMES_CONTADORES)


def css_institucional() -> str:
    """Retorna o conteúdo do CSS institucional (34 classes oficiais do SEI)."""
    return obter_estilos_sei()


def montar_html(corpo_html: str, css: str | None = None) -> str:
    """Envolve o corpo em um documento HTML com CSS institucional e contadores para preview."""
    css_content = css if css is not None else css_institucional()
    # Os contadores nascem no body::before, irmão dos parágrafos, e não no body. Pela regra
    # de herança de contadores do CSS, o contador do pai encobre o que um irmão anterior
    # criou com o mesmo nome: com o reset no body, o Chrome ignorava o counter-reset de cada
    # Item_Nivel1 e emendava os subitens (2.3 logo depois de 2.). O comentário fica aqui, e
    # não no <style>, para não ir em cada arquivo gerado.
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{TITULO_DA_SAIDA}</title>
<style>
body {{font-family:Calibri, sans-serif; font-size:12pt; color:#000; background:#fff;
      max-width:19cm; margin:1.5em auto; padding:0 1em;}}
body::before {{content:""; display:block; counter-reset:{COUNTER_RESET_INICIAL};}}
table {{border-collapse:collapse;}}
ul {{margin:6pt 6pt 6pt 40px; padding-left:20px;}}
li {{font-size:12pt; font-family:Calibri; text-align:justify; margin:3pt 0;}}
{css_content}
</style>
</head>
<body>
<!-- ============================================================
     COMO USAR (este comentário NÃO é copiado):
     1. Abra este arquivo no Chrome / navegador
     2. Cmd+A (selecionar tudo) e Cmd+C (copiar)
     3. No editor do documento SEI, clique no corpo e Cmd+V
     4. Confira a numeração automática e as tabelas; depois Salvar
     ============================================================ -->
{corpo_html}
</body>
</html>
"""


def apagar_partes_antigas(saida: str | Path) -> list[Path]:
    """Apaga as partes (`_parte01.html`...) que versões anteriores gravaram para esta saída.

    Até a versão 0.5, o documento longo era dividido em partes para o plugin SEI Pro.
    Sem esta limpeza, quem converte de novo na mesma pasta ficaria com o arquivo único
    novo ao lado das partes velhas, sem saber qual colar.
    """
    caminho = Path(saida)
    removidos: list[Path] = []
    for f in caminho.parent.glob(f"{caminho.stem}_parte*{caminho.suffix}"):
        try:
            f.unlink()
            removidos.append(f)
        except OSError:
            pass
    return removidos


def derivar_caminho_saida(
    entrada: str | Path,
    so_corpo: bool = False,
    outdir: str | Path | None = None,
) -> Path:
    """Deriva o caminho do arquivo de saída SEI a partir da entrada."""
    p_in = Path(entrada)
    stem = p_in.stem

    if stem.startswith("Nota_Tecnica_Revisada_"):
        identificador = stem[len("Nota_Tecnica_Revisada_"):]
        base_saida = f"Nota_Tecnica_SEI_{identificador}"
    elif stem.startswith("Nota_Tecnica_"):
        identificador = stem[len("Nota_Tecnica_"):]
        base_saida = f"Nota_Tecnica_SEI_{identificador}"
    else:
        base_saida = f"{stem}_SEI"

    sufixo = "_corpo.html" if so_corpo else ".html"
    destino_pasta = Path(outdir) if outdir else p_in.parent
    return destino_pasta / f"{base_saida}{sufixo}"
