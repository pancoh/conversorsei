import json

import pytest

from conversorsei.cli import main
from conversorsei.core import converter_diretorio, converter_documento


def test_core_converter_documento_md(tmp_path):
    md_file = tmp_path / "minuta.md"
    md_file.write_text("# 1. ASSUNTO\n\n1.1. Texto do assunto.", encoding="utf-8")

    res = converter_documento(md_file, outdir=tmp_path / "saida")
    assert res.sucesso
    assert len(res.arquivos_gerados) == 1
    assert (tmp_path / "saida" / "minuta_SEI.html").is_file()


def test_core_converter_diretorio(tmp_path):
    pasta_entrada = tmp_path / "entrada"
    pasta_saida = tmp_path / "saida"
    pasta_entrada.mkdir()

    (pasta_entrada / "doc1.md").write_text("# 1. ASSUNTO\n\n1.1. Texto 1", encoding="utf-8")
    (pasta_entrada / "doc2.txt").write_text("1. ASSUNTO\n\n1.1. Texto 2", encoding="utf-8")

    resultados = converter_diretorio(pasta_entrada, outdir=pasta_saida)
    assert len(resultados) == 2
    assert all(r.sucesso for r in resultados)
    assert (pasta_saida / "doc1_SEI.html").is_file()
    assert (pasta_saida / "doc2_SEI.html").is_file()


def test_core_converter_diretorio_com_subpastas(tmp_path):
    pasta_entrada = tmp_path / "dados" / "entrada"
    pasta_saida = tmp_path / "dados" / "saida"
    sub_processo = pasta_entrada / "80000.001234_2026-10"
    sub_processo.mkdir(parents=True)

    (sub_processo / "nota.md").write_text("# 1. ASSUNTO\n\n1.1. Texto", encoding="utf-8")
    (pasta_entrada / "avulso.md").write_text("# 1. ASSUNTO\n\n1.1. Avulso", encoding="utf-8")

    resultados = converter_diretorio(pasta_entrada, outdir=pasta_saida, recursivo=True)
    assert len(resultados) == 2
    assert (pasta_saida / "80000.001234_2026-10" / "nota_SEI.html").is_file()
    assert (pasta_saida / "avulso_SEI.html").is_file()


def test_cli_conversao_json(tmp_path, capsys):
    md_file = tmp_path / "teste.md"
    md_file.write_text("# 1. ASSUNTO\n\n1.1. Parágrafo único.", encoding="utf-8")

    exit_code = main([str(md_file), "-o", str(tmp_path / "saida_cli"), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    dados = json.loads(captured.out)
    assert len(dados) == 1
    assert dados[0]["sucesso"] is True
    assert len(dados[0]["gerados"]) == 1
    # Os mesmos campos que a interface web recebe
    assert dados[0]["citacoes_trechos"] == []
    assert dados[0]["cabecalho_trechos"] == []


def test_cli_saida_com_varios_alvos_e_recusada(tmp_path, capsys):
    """--saida nomeia um arquivo só: com pasta ou vários arquivos, antes era ignorada em silêncio."""
    um = tmp_path / "um.md"
    dois = tmp_path / "dois.md"
    for arquivo in (um, dois):
        arquivo.write_text("1. ASSUNTO\n\nTexto.", encoding="utf-8")

    assert main([str(um), str(dois), "--saida", str(tmp_path / "fixo.html")]) == 1
    assert main([str(tmp_path), "--saida", str(tmp_path / "fixo.html")]) == 1
    assert "--saida" in capsys.readouterr().err
    assert not (tmp_path / "fixo.html").exists()



def test_cli_corpo_gera_fragmento_sem_head(tmp_path):
    """--corpo entrega só o fragmento, sem <head> nem <style>."""
    entrada = tmp_path / "minuta.md"
    entrada.write_text("# 1. ASSUNTO\n\n1.1. Texto do corpo.", encoding="utf-8")

    assert main([str(entrada), "-o", str(tmp_path), "--corpo"]) == 0

    gerado = tmp_path / "minuta_SEI_corpo.html"
    conteudo = gerado.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" not in conteudo
    assert "<style>" not in conteudo
    assert 'class="Item_Nivel1"' in conteudo


def test_cli_converte_documento_longo_em_um_arquivo_e_apaga_partes_antigas(tmp_path):
    """O documento longo sai num arquivo só, e as partes de versões anteriores saem da pasta."""
    linhas = []
    for i in range(1, 40):
        linhas.append(f"# {i}. SECAO {i}")
        linhas.append("Texto de preenchimento. " * 40)
    entrada = tmp_path / "grande.md"
    entrada.write_text("\n\n".join(linhas), encoding="utf-8")
    (tmp_path / "grande_SEI_parte01.html").write_text("parte antiga", encoding="utf-8")

    assert main([str(entrada), "-o", str(tmp_path)]) == 0
    assert (tmp_path / "grande_SEI.html").is_file()
    assert not list(tmp_path.glob("grande_SEI_parte*.html"))


def test_cli_recusa_as_opcoes_de_divisao_retiradas(tmp_path):
    """--unico, --partes e --max-kb saíram com a divisão em partes."""
    entrada = tmp_path / "doc.md"
    entrada.write_text("# 1. ASSUNTO\n\n1.1. Texto.", encoding="utf-8")

    for opcao in (["--unico"], ["--partes"], ["--max-kb", "18"]):
        with pytest.raises(SystemExit):
            main([str(entrada), "-o", str(tmp_path), *opcao])


def test_cli_max_nivel_so_aceita_os_niveis_do_sei(tmp_path):
    """O SEI tem Item_Nivel1 a 4: 0 ou 5 gerariam classe que o editor não conhece."""
    entrada = tmp_path / "doc.md"
    entrada.write_text("1. ASSUNTO\n\n1.1.1.1.1. Quinto nível.", encoding="utf-8")

    for valor in ("0", "5", "x"):
        with pytest.raises(SystemExit):
            main([str(entrada), "-o", str(tmp_path), "--max-nivel", valor])


def test_core_max_nivel_acima_de_4_nao_gera_classe_inexistente(tmp_path):
    entrada = tmp_path / "doc.md"
    entrada.write_text("1. ASSUNTO\n\n1.1.1.1.1. Quinto nível.", encoding="utf-8")

    res = converter_documento(entrada, outdir=tmp_path / "saida", max_nivel=5)
    html = res.arquivos_gerados[0].read_text(encoding="utf-8")
    assert "Item_Nivel5" not in html
    assert '<p class="Item_Alinea_Letra">Quinto nível.</p>' in html
    assert not res.avisos


def test_core_converte_readme_quando_solicitado(tmp_path):
    """README.md deixou de ser descartado em silêncio pela varredura de diretório."""
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    (pasta / "README.md").write_text("# 1. ASSUNTO\n\n1.1. Conteudo do readme.", encoding="utf-8")

    resultados = converter_diretorio(pasta, outdir=tmp_path / "saida")
    assert len(resultados) == 1
    assert (tmp_path / "saida" / "README_SEI.html").is_file()


def test_exemplo_do_repositorio_converte_sem_avisos(tmp_path):
    """O documento de exemplo precisa continuar convertendo limpo (é o que o README indica)."""
    from pathlib import Path

    exemplo = Path(__file__).resolve().parent.parent / "exemplos" / "nota_tecnica_exemplo.md"
    resultado = converter_documento(exemplo, outdir=tmp_path)

    assert resultado.sucesso, resultado.erros
    assert resultado.avisos == []

    html = resultado.arquivos_gerados[0].read_text(encoding="utf-8")
    assert 'class="Item_Nivel1"' in html
    assert "<table" in html
    assert '<li class="Texto_Justificado">' in html


def test_watch_so_converte_arquivo_estabilizado(tmp_path):
    """A gravação do Word acontece em etapas, e o arquivo só é lido quando para de mudar."""
    from conversorsei.cli import ciclo_de_observacao

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    doc = entrada / "minuta.md"
    doc.write_text("# 1. ASSUNTO\n\n1.1. Primeira versão.", encoding="utf-8")

    convertidos: dict = {}
    pendentes: dict = {}

    # Primeira varredura só registra: o arquivo pode estar em meio à gravação
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == []
    # Na segunda, o arquivo continua igual e está pronto
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == [doc]
    # Sem alteração, não converte de novo
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == []


def test_watch_reconverte_apos_alteracao_e_esquece_removido(tmp_path):
    from conversorsei.cli import ciclo_de_observacao

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    doc = entrada / "minuta.md"
    doc.write_text("# 1. ASSUNTO", encoding="utf-8")

    convertidos: dict = {}
    pendentes: dict = {}
    ciclo_de_observacao([str(entrada)], False, convertidos, pendentes)
    ciclo_de_observacao([str(entrada)], False, convertidos, pendentes)

    doc.write_text("# 1. ASSUNTO\n\n1.1. Texto acrescentado depois.", encoding="utf-8")
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == []
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == [doc]

    doc.unlink()
    assert ciclo_de_observacao([str(entrada)], False, convertidos, pendentes) == []
    assert convertidos == {} and pendentes == {}


def test_watch_ignora_formato_nao_suportado_e_saida_gerada(tmp_path):
    """O HTML gerado não pode realimentar a observação quando a saída fica dentro da entrada."""
    from conversorsei.cli import arquivos_observaveis

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "minuta.md").write_text("# 1. ASSUNTO", encoding="utf-8")
    (entrada / "minuta_SEI.html").write_text("<p>gerado</p>", encoding="utf-8")
    (entrada / "planilha.xlsx").write_bytes(b"nao suportado")

    observados = arquivos_observaveis([str(entrada)], recursivo=False)
    assert [p.name for p in observados] == ["minuta.md"]


def test_watch_recusa_saida_com_nome_fixo(tmp_path, capsys):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "minuta.md").write_text("# 1. ASSUNTO", encoding="utf-8")

    codigo = main([str(entrada), "--watch", "--saida", str(tmp_path / "fixo.html")])
    assert codigo == 1
    assert "não combina com --watch" in capsys.readouterr().err


def test_watch_converte_e_encerra_no_ctrl_c(tmp_path, monkeypatch, capsys):
    """O laço converte o que apareceu e sai limpo no Ctrl+C, sem estourar exceção."""
    import conversorsei.cli as cli

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "minuta.md").write_text("# 1. ASSUNTO\n\n1.1. Texto.", encoding="utf-8")

    saida = tmp_path / "saida"
    chamadas = {"n": 0}

    def falso_sleep(_segundos):
        chamadas["n"] += 1
        # Deixa duas varreduras acontecerem (registro e conversão) antes de encerrar
        if chamadas["n"] >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", falso_sleep)

    codigo = main([str(entrada), "--watch", "-o", str(saida)])
    assert codigo == 0

    out = capsys.readouterr().out
    assert "Observando" in out
    assert "minuta.md ->" in out
    assert "Observação encerrada." in out
    assert (saida / "minuta_SEI.html").is_file()


def test_rtf_em_pasta_vira_falha_com_orientacao_e_nao_some(tmp_path, capsys):
    """Antes aceito, o .rtf deixado na pasta de entrada vira falha explicada, e não some.

    Vale para a pasta, para a API (converter_diretorio), para o watch e para o --json, que
    sai com código 1. Arquivo de trava do Word (~$) continua ignorado.
    """
    import json

    from conversorsei.cli import arquivos_observaveis, main

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "contrato.rtf").write_bytes(b"{\\rtf1 texto}")
    (entrada / "~$contrato.rtf").write_bytes(b"{\\rtf1 texto}")
    (entrada / "nota.md").write_text("Texto.", encoding="utf-8")

    resultados = {r.arquivo_origem.name: r for r in converter_diretorio(entrada, outdir=tmp_path / "api")}
    assert set(resultados) == {"contrato.rtf", "nota.md"}
    assert not resultados["contrato.rtf"].sucesso
    assert "não é mais aceito" in resultados["contrato.rtf"].erros[0]
    assert ".docx ou .odt" in resultados["contrato.rtf"].erros[0]

    assert main([str(entrada), "-o", str(tmp_path / "saida")]) == 1
    saida = capsys.readouterr()
    assert "não é mais aceito" in saida.out + saida.err
    assert (tmp_path / "saida" / "nota_SEI.html").exists()

    assert main([str(entrada / "contrato.rtf"), "--json", "-o", str(tmp_path / "saida")]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["sucesso"] is False

    # O watch enxerga o .rtf que chegar depois, inclusive passado direto como alvo
    observados = {p.name for p in arquivos_observaveis([str(entrada)], recursivo=False)}
    assert observados == {"contrato.rtf", "nota.md"}
    assert arquivos_observaveis([str(entrada / "contrato.rtf")], recursivo=False)


def test_doc_em_pasta_vira_falha_com_orientacao_e_nao_some(tmp_path):
    """O .doc deixado na pasta de entrada recebe a orientação, como o .rtf."""
    from conversorsei.cli import arquivos_observaveis

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "oficio.doc").write_bytes(b"\xd0\xcf\x11\xe0")

    resultados = converter_diretorio(entrada, outdir=tmp_path / "saida")
    assert [r.arquivo_origem.name for r in resultados] == ["oficio.doc"]
    assert not resultados[0].sucesso
    assert "salve como .docx ou .odt" in resultados[0].erros[0]
    assert {p.name for p in arquivos_observaveis([str(entrada)], recursivo=False)} == {"oficio.doc"}


def test_cli_sem_cabecalho_omite_e_informa(tmp_path, capsys):
    entrada = tmp_path / "nota.md"
    entrada.write_text("# NOTA TÉCNICA Nº 1\n\n## 1. ASSUNTO\n\nTexto.\n", encoding="utf-8")
    saida = tmp_path / "saida"

    assert main([str(entrada), "--sem-cabecalho", "-o", str(saida)]) == 0
    assert "1 parágrafo antes do item 1 foi omitido" in capsys.readouterr().out
    html = (saida / "nota_SEI.html").read_text(encoding="utf-8")
    assert "NOTA TÉCNICA" not in html
    assert 'class="Item_Nivel1"' in html

    assert main([str(entrada), "-o", str(saida)]) == 0
    assert "cabeçalho:" not in capsys.readouterr().out
    assert "NOTA TÉCNICA" in (saida / "nota_SEI.html").read_text(encoding="utf-8")


@pytest.mark.parametrize('nomes', [('nota.md', 'nota.txt'), ('Nota_Tecnica_12.md', 'Nota_Tecnica_Revisada_12.txt')])
def test_lote_recusa_destinos_coincidentes_sem_apagar_a_primeira_saida(tmp_path, nomes):
    for indice, nome in enumerate(nomes):
        (tmp_path / nome).write_text(f'Texto do documento {indice}.', encoding='utf-8')
    resultados = converter_diretorio(tmp_path, outdir=tmp_path / 'saida')
    assert [r.sucesso for r in resultados] == [True, False]
    assert 'coincide' in resultados[1].erros[0]
    conteudo = resultados[0].arquivos_gerados[0].read_text(encoding='utf-8')
    assert 'Texto do documento 0.' in conteudo
    assert 'Texto do documento 1.' not in conteudo


def test_cli_controla_colisoes_entre_alvos_independentes(tmp_path, capsys):
    entradas = [tmp_path / nome for nome in ('nota.md', 'nota.txt')]
    for indice, entrada in enumerate(entradas):
        entrada.write_text(f'Documento {indice}.', encoding='utf-8')
    assert main([*(str(e) for e in entradas), '-o', str(tmp_path / 'saida'), '--json']) == 1
    assert [r['sucesso'] for r in json.loads(capsys.readouterr().out)] == [True, False]


def test_saida_explicita_nao_pode_substituir_a_entrada(tmp_path):
    entrada = tmp_path / 'original.html'
    texto = '<p>Texto original.</p>'
    entrada.write_text(texto, encoding='utf-8')
    resultado = converter_documento(entrada, caminho_saida=entrada)
    assert not resultado.sucesso
    assert entrada.read_text(encoding='utf-8') == texto


def test_watch_conserva_subpastas_e_controla_colisoes(tmp_path, monkeypatch, capsys):
    import conversorsei.cli as cli

    entrada = tmp_path / 'entrada'
    for pasta in ('um', 'dois'):
        subpasta = entrada / pasta
        subpasta.mkdir(parents=True)
        (subpasta / 'nota.md').write_text(f'Documento {pasta}.', encoding='utf-8')
    (entrada / 'um' / 'nota.txt').write_text('Outra origem.', encoding='utf-8')
    chamadas = 0

    def encerrar(_segundos):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, 'sleep', encerrar)
    saida = tmp_path / 'saida'
    assert main([str(entrada), '-r', '-w', '-o', str(saida)]) == 0
    for pasta in ('um', 'dois'):
        assert f'Documento {pasta}.' in (saida / pasta / 'nota_SEI.html').read_text(encoding='utf-8')
    assert 'coincide' in capsys.readouterr().err
    assert not (saida / 'nota_SEI.html').exists()
