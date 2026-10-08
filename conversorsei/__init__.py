"""
conversorsei — Pacote Python para conversão universal de documentos (DOCX, PDF, ODT, HTML, MD, TXT)
para o padrão institucional do editor do SEI.
"""
from conversorsei.core import (
    EXTENSOES_SUPORTADAS,
    ArquivoSEI,
    ResultadoConversao,
    ResultadoMemoria,
    converter_bytes,
    converter_diretorio,
    converter_documento,
)
from conversorsei.docx_converter import (
    converter_docx_para_blocos,
    converter_docx_para_html,
)
from conversorsei.html_converter import (
    converter_html_para_blocos,
    extrair_markdown_html,
)
from conversorsei.md_converter import (
    converter_md_para_blocos,
    converter_md_para_html,
    converter_texto_md_para_blocos,
    markdown_para_docx,
)
from conversorsei.montagem import (
    css_institucional,
    derivar_caminho_saida,
    montar_html,
)
from conversorsei.odt_converter import (
    converter_odt_para_blocos,
    converter_odt_para_html,
    extrair_markdown_odt,
)
from conversorsei.pdf_converter import (
    converter_pdf_para_blocos,
    converter_pdf_para_html,
    extrair_texto_pdf,
    limpar_boilerplate_sei,
)
from conversorsei.validador import validar_arquivo_sei, validar_html_sei
from conversorsei.web import converter_documento_memoria, converter_memoria_json

__version__ = "0.6.1"
__all__ = [
    "EXTENSOES_SUPORTADAS",
    "ArquivoSEI",
    "ResultadoConversao",
    "ResultadoMemoria",
    "converter_bytes",
    "converter_diretorio",
    "converter_documento",
    "converter_documento_memoria",
    "converter_docx_para_blocos",
    "converter_docx_para_html",
    "converter_html_para_blocos",
    "converter_md_para_blocos",
    "converter_md_para_html",
    "converter_memoria_json",
    "converter_odt_para_blocos",
    "converter_odt_para_html",
    "converter_pdf_para_blocos",
    "converter_pdf_para_html",
    "converter_texto_md_para_blocos",
    "css_institucional",
    "derivar_caminho_saida",
    "extrair_markdown_html",
    "extrair_markdown_odt",
    "extrair_texto_pdf",
    "limpar_boilerplate_sei",
    "markdown_para_docx",
    "montar_html",
    "validar_arquivo_sei",
    "validar_html_sei",
]
