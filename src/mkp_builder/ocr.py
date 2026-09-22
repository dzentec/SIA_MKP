"""OCR routing and pipeline options configuration."""

from __future__ import annotations

import logging
from typing import Literal

try:
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
        TesseractOcrOptions,
    )
except ImportError:
    class PdfPipelineOptions:  # type: ignore
        def __init__(self):
            self.generate_picture_images = True
            self.images_scale = 2.0
            self.do_ocr = False
            self.ocr_options = None

    class RapidOcrOptions:  # type: ignore
        def __init__(self, **kwargs):
            pass

    class TesseractOcrOptions:  # type: ignore
        def __init__(self, **kwargs):
            pass

logger = logging.getLogger(__name__)

OcrProfile = Literal["digital", "scanned", "mixed"]
OcrEngine = Literal["rapidocr", "tesseract"]


def build_pipeline_options(
    profile: OcrProfile = "digital",
    ocr_engine: OcrEngine = "rapidocr",
    tessdata_path: str | None = None,
    images_scale: float = 2.0,
    generate_picture_images: bool = True,
) -> PdfPipelineOptions:
    """Build Docling PdfPipelineOptions according to profile and engine."""
    opts = PdfPipelineOptions()
    opts.generate_picture_images = generate_picture_images
    opts.images_scale = images_scale

    need_ocr = profile in ("scanned", "mixed")
    opts.do_ocr = need_ocr

    if need_ocr:
        full_page = (profile == "scanned")
        if ocr_engine == "tesseract":
            kwargs = {"lang": ["rus", "eng"]}
            if tessdata_path:
                kwargs["path"] = tessdata_path
            opts.ocr_options = TesseractOcrOptions(**kwargs)
            logger.info("Configured Tesseract OCR options (full_page=%s)", full_page)
        else:
            opts.ocr_options = RapidOcrOptions()
            logger.info("Configured RapidOCR options (full_page=%s)", full_page)
    else:
        logger.info("OCR disabled for profile '%s'", profile)

    return opts


def is_text_density_low(text: str, min_chars: int = 50) -> bool:
    """Check if extracted page text is below density threshold (indicating scanned page in mixed mode)."""
    cleaned = "".join(text.split())
    return len(cleaned) < min_chars
