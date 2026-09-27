"""Testes do empacotador do bundle web (scripts/bundle_web.py)."""
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bundle_web", RAIZ / "scripts" / "bundle_web.py")
bundle_web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle_web)


def test_bundle_e_deterministico():
    """Duas gerações seguidas produzem bytes idênticos (permite verificar sincronia no CI)."""
    primeiro, arquivos = bundle_web.gerar_bytes_zip()
    segundo, _ = bundle_web.gerar_bytes_zip()
    assert primeiro == segundo
    assert "conversao_sei/web.py" in arquivos
    assert "conversao_sei/recursos/estilos_sei.css" in arquivos
    assert not any("__pycache__" in a for a in arquivos)


def test_bundle_versionado_esta_sincronizado():
    """docs/conversao_sei.zip precisa refletir o código-fonte atual."""
    assert bundle_web.verificar_bundle() is True


def test_index_chama_a_versao_atual_do_app_e_do_css():
    """Regressão: sem marca de versão, o cache entregou o HTML novo com o app.js antigo."""
    assert bundle_web.verificar_versoes() is True


def test_marca_de_versao_troca_so_a_marca():
    html = '<link href="estilos.css?v=abc" rel="stylesheet"><script src="app.js"></script>'
    novo = bundle_web.index_com_versoes(html)
    assert novo == (
        f'<link href="estilos.css?v={bundle_web.marca_de_versao("estilos.css")}" rel="stylesheet">'
        f'<script src="app.js?v={bundle_web.marca_de_versao("app.js")}"></script>'
    )
