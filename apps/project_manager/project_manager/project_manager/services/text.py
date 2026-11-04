"""Text helpers for Vietnamese input: comparing without accents, stable ASCII keys."""

import re
import unicodedata


def plain(text) -> str:
    """Lower case, no accents, single spaces: "  Mã  WBS " -> "ma wbs"."""
    text = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").lower().split())


def slug(text, fallback: str = "truong") -> str:
    """A key made of a-z, 0-9 and _: "Khối lượng (m3)" -> "khoi_luong_m3"."""
    return re.sub(r"[^a-z0-9]+", "_", plain(text)).strip("_") or fallback
