from __future__ import annotations

import re
import unicodedata

UI_NOISE = [
    "Like", "Comment", "Share", "See more", "Most relevant",
    "Write a comment", "Send", "Translate",
    "אהבתי", "הגב", "שתף", "ראה עוד", "הצג עוד", "עוד",
    "תגובה", "שתפו", "כתוב תגובה",
]

_NOISE_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(n) for n in UI_NOISE) + r")$",
    re.MULTILINE,
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _NOISE_PATTERN.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_phone_numbers(text: str) -> list[str]:
    pattern = re.compile(
        r"(?:(?:\+972|972|0)[-\s]?)"
        r"(?:5[0-9]|7[2-9]|[2-9])"
        r"[-\s]?\d{3}[-\s]?\d{4}"
    )
    raw = pattern.findall(text)
    cleaned = []
    for p in raw:
        digits = re.sub(r"[^\d+]", "", p)
        cleaned.append(digits)
    return list(dict.fromkeys(cleaned))


def canonicalize_facebook_url(url: str) -> str:
    url = url.split("?")[0]
    url = url.replace("m.facebook.com", "www.facebook.com")
    url = url.replace("mbasic.facebook.com", "www.facebook.com")
    url = url.rstrip("/")
    return url
