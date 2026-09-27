from pathlib import Path


def obter_estilos_sei() -> str:
    css_path = Path(__file__).parent / "estilos_sei.css"
    if css_path.is_file():
        return css_path.read_text(encoding="utf-8")
    return ""
