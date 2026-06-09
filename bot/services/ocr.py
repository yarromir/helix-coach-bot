"""ocr для распознавания анализов (фото/скрин/pdf).

поддержка двух движков: pytesseract (по умолчанию) и easyocr.
тяжёлые зависимости импортируются лениво — импорт модуля не падает без них.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from bot.config import config

logger = logging.getLogger(__name__)


class OCRUnavailable(RuntimeError):
    pass


@dataclass
class OCRResult:
    text: str
    low_confidence: bool


def _images_from_path(path: str) -> list:
    from PIL import Image

    p = Path(path)
    if p.suffix.lower() == ".pdf":
        try:
            from pdf2image import convert_from_path
        except Exception as e:  # noqa: BLE001
            raise OCRUnavailable(f"для pdf нужен pdf2image/poppler: {e}") from e
        return convert_from_path(path)
    return [Image.open(path)]


def _ocr_tesseract(images: list) -> OCRResult:
    try:
        import pytesseract
    except Exception as e:  # noqa: BLE001
        raise OCRUnavailable(f"pytesseract не установлен: {e}") from e

    texts: list[str] = []
    confidences: list[float] = []
    for img in images:
        texts.append(pytesseract.image_to_string(img, lang="rus+eng"))
        try:
            data = pytesseract.image_to_data(
                img, lang="rus+eng", output_type=pytesseract.Output.DICT
            )
            confidences += [float(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit()]
        except Exception:  # noqa: BLE001
            pass
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(text="\n".join(texts).strip(), low_confidence=mean_conf < 60)


def _ocr_easyocr(images: list) -> OCRResult:
    try:
        import easyocr
        import numpy as np
    except Exception as e:  # noqa: BLE001
        raise OCRUnavailable(f"easyocr не установлен: {e}") from e

    reader = easyocr.Reader(["ru", "en"], gpu=False)
    texts: list[str] = []
    confidences: list[float] = []
    for img in images:
        results = reader.readtext(np.array(img))
        for _box, text, conf in results:
            texts.append(text)
            confidences.append(float(conf))
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(text="\n".join(texts).strip(), low_confidence=mean_conf < 0.6)


def extract_text(path: str) -> OCRResult:
    """распознаёт текст из изображения/pdf выбранным движком."""
    images = _images_from_path(path)
    if config.ocr_engine == "easyocr":
        return _ocr_easyocr(images)
    return _ocr_tesseract(images)
