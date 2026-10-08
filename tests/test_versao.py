"""Versão do sistema e histórico (CHANGELOG.md).

A versão do pyproject.toml é a que vale. O pacote, a última versão do CHANGELOG.md e o
rodapé da página precisam dizer o mesmo número, e o quadro Novidades sai do mesmo
arquivo. O bundle_web.py grava a página, e o CI confere com --verificar.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

import conversorsei

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bundle_web", RAIZ / "scripts" / "bundle_web.py")
bundle_web = importlib.util.module_from_spec(spec)
# O dataclass do script procura o módulo em sys.modules
sys.modules["bundle_web"] = bundle_web
spec.loader.exec_module(bundle_web)


def historico_atual() -> list:
    return bundle_web.ler_historico((RAIZ / "CHANGELOG.md").read_text(encoding="utf-8"))


def test_pacote_changelog_e_pagina_dizem_a_mesma_versao():
    projeto = bundle_web.versao_do_projeto()
    assert conversorsei.__version__ == projeto
    assert bundle_web.ultima_versao(historico_atual()).numero == projeto
    rodape = re.search(r'<span id="versao-atual">([^<]*)</span>', (RAIZ / "docs" / "index.html").read_text())
    assert rodape and rodape.group(1) == projeto


def test_versoes_do_historico_vem_da_mais_recente_para_a_mais_antiga():
    lancadas = [v for v in historico_atual() if v.numero]
    numeros = [tuple(int(n) for n in v.numero.split(".")) for v in lancadas]
    assert numeros == sorted(numeros, reverse=True)
    assert len(set(numeros)) == len(numeros)
    assert all(v.blocos for v in lancadas), "versão lançada sem nenhuma mudança descrita"


HISTORICO = """# Histórico

## Em desenvolvimento

- **Novo.** Item ainda sem número,
  em duas linhas.

## 1.1.0 (2026-01-02)

Texto de abertura com <tag> e & solto.

- **Primeiro.** Um item.
- Segundo item.

## 1.0.0 (2025-12-31)

- Versão inicial.
"""


def test_le_titulos_paragrafos_e_itens_com_continuacao():
    versoes = bundle_web.ler_historico(HISTORICO)
    assert [v.numero for v in versoes] == [None, "1.1.0", "1.0.0"]
    assert versoes[0].blocos == [("li", "**Novo.** Item ainda sem número, em duas linhas.")]
    assert versoes[1].data == "2 de janeiro de 2026"
    assert [tipo for tipo, _ in versoes[1].blocos] == ["p", "li", "li"]


def test_titulo_fora_do_padrao_e_erro():
    with pytest.raises(ValueError, match="fora do padrão"):
        bundle_web.ler_historico("## 1.2.0 - 2026-01-02\n\n- Item.\n")


def test_versao_do_pyproject_diferente_do_changelog_e_erro(monkeypatch):
    monkeypatch.setattr(bundle_web, "versao_do_projeto", lambda: "1.0.0")
    with pytest.raises(ValueError, match="mude os dois juntos"):
        bundle_web.ultima_versao(bundle_web.ler_historico(HISTORICO))


def test_html_das_novidades_escapa_o_texto_e_traduz_o_negrito():
    html = bundle_web.html_das_novidades(bundle_web.ler_historico(HISTORICO))
    assert "&lt;tag&gt; e &amp; solto" in html
    assert "<strong>Primeiro.</strong> Um item." in html
    assert "Versão 1.1.0" in html and "2 de janeiro de 2026" in html
    # Em desenvolvimento aparece quando tem item, antes das versões lançadas
    assert html.index("Em desenvolvimento") < html.index("Versão 1.1.0")
    vazio = HISTORICO.replace("- **Novo.** Item ainda sem número,\n  em duas linhas.\n", "")
    assert "Em desenvolvimento" not in bundle_web.html_das_novidades(bundle_web.ler_historico(vazio))


def test_crases_do_historico_viram_codigo_no_quadro():
    """O histórico cita opções da linha de comando entre crases, que não podem aparecer cruas."""
    assert bundle_web._inline("Saem `--unico` e `<x>`.") == "Saem <code>--unico</code> e <code>&lt;x&gt;</code>."
    assert "`" not in (RAIZ / "docs" / "index.html").read_text(encoding="utf-8").split("novidades:inicio")[1]


def test_notas_da_release_tem_cada_bloco_numa_linha(monkeypatch, tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(HISTORICO, encoding="utf-8")
    monkeypatch.setattr(bundle_web, "CHANGELOG", changelog)
    assert bundle_web.notas_da_versao("1.1.0") == (
        "Texto de abertura com <tag> e & solto.\n\n- **Primeiro.** Um item.\n- Segundo item.\n"
    )
    with pytest.raises(ValueError, match="não está no CHANGELOG"):
        bundle_web.notas_da_versao("9.9.9")
