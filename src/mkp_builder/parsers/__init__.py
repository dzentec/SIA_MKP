"""Document parsers package for MKP builder."""

from pathlib import Path
from mkp_builder.parsers.base import ParsedDocument, ParsedPage, ParsedFigure, ParsedTable
from mkp_builder.parsers.pdf_parser import PDFParser
from mkp_builder.parsers.epub_parser import EPUBParser
from mkp_builder.parsers.docx_parser import DOCXParser
from mkp_builder.ocr import OcrProfile, OcrEngine


def get_parser(
    file_path: Path | str,
    profile: OcrProfile = "digital",
    ocr_engine: OcrEngine = "rapidocr",
    tessdata_path: str | None = None,
):
    """Factory to get the appropriate parser based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return PDFParser(profile=profile, ocr_engine=ocr_engine, tessdata_path=tessdata_path)
    elif ext == ".epub":
        return EPUBParser()
    elif ext in (".docx", ".doc"):
        return DOCXParser()
    else:
        raise ValueError(f"Unsupported document format: {ext}")
