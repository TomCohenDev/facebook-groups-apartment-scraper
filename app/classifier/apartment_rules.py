from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from app.utils.text import extract_phone_numbers
from app.utils.time import parse_entry_date

LISTING_KEYWORDS = [
    "להשכרה", "דירה", "חדרים", "חד'", "כניסה", "פינוי", "שכירות", "ללא תיווך",
]

NEGATIVE_PHRASES = [
    "מחפש דירה", "מחפשת דירה", "מחפש להשכרה", "מחפשת להשכרה",
    "דרוש שותף", "דרושה שותפה", "שותף לדירה", "שותפה לדירה",
]

NEGATIVE_START = re.compile(r"^(מחפש|מחפשת|דרוש|דרושה)\b")

_PRICE_PATTERNS = [
    re.compile(r"₪\s*([\d,]+)"),
    re.compile(r"([\d,]+)\s*(?:₪|ש[\"״]?ח|שח)"),
    re.compile(r"([\d.]+)\s*אלף"),
]

_ROOMS_PATTERNS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:חדרים|חד['’])"),
    re.compile(r"(שני|שלושה|ארבעה|חמישה)\s*חדרים"),
    re.compile(r"חדר\s+וחצי"),
]
_ROOMS_WORDS = {"שני": 2, "שלושה": 3, "ארבעה": 4, "חמישה": 5}

_CITY_NAMES = [
    "תל אביב", "גבעתיים", "רמת גן", "פתח תקווה", "חולון", "בת ים",
    "רמת השרון", "הרצליה", "כפר סבא", "ראש העין",
]

_NEIGHBORHOOD_NAMES = [
    "פלורנטין", "לב העיר", "הצפון הישן", "הצפון החדש", "הדר יוסף",
    "בורוכוב", "הגבעה", "שכונת התקווה", "נווה שאנן", "כרם התימנים",
]


class ApartmentExtraction(BaseModel):
    is_listing: bool
    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    price_ils: int | None = None
    rooms: float | None = None
    sqm: int | None = None
    floor: int | None = None
    entry_date: date | None = None
    brokerage: bool | None = None
    pets_allowed: bool | None = None
    furnished: bool | None = None
    has_balcony: bool | None = None
    has_parking: bool | None = None
    has_mamad: bool | None = None
    phone_numbers: list[str] = []
    confidence: float = 0.0
    reasons: list[str] = []


def passes_keyword_gate(text: str) -> bool:
    for phrase in NEGATIVE_PHRASES:
        if phrase in text:
            return False
    if NEGATIVE_START.search(text):
        return False
    for kw in LISTING_KEYWORDS:
        if kw in text:
            return True
    return False


def _parse_price(text: str) -> int | None:
    for pattern in _PRICE_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).replace(",", "").strip()
            try:
                val = float(raw)
                if val < 100:
                    val *= 1000
                return int(val)
            except ValueError:
                pass
    return None


def _parse_rooms(text: str) -> float | None:
    if "חדר וחצי" in text:
        return 1.5
    m = _ROOMS_PATTERNS[0].search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = _ROOMS_PATTERNS[1].search(text)
    if m:
        return float(_ROOMS_WORDS.get(m.group(1), 0))
    return None


def _parse_sqm(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:מ[\"״]?ר|מטר)", text)
    if m:
        return int(m.group(1))
    return None


def _parse_floor(text: str) -> int | None:
    m = re.search(r"קומה\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def _parse_brokerage(text: str) -> bool | None:
    if re.search(r"ללא תיווך|בלי תיווך|לא מתיווך", text):
        return False
    if re.search(r"\bתיווך\b", text):
        return True
    return None


def _find_city(text: str) -> str | None:
    for city in _CITY_NAMES:
        if city in text:
            return city
    return None


def _find_neighborhood(text: str) -> str | None:
    for hood in _NEIGHBORHOOD_NAMES:
        if hood in text:
            return hood
    return None


def _find_entry_date(text: str) -> date | None:
    patterns = [
        r"(?:כניסה|פינוי|מ-?|מתאריך|מ?ה?-?)(\S+(?:\s+\S+)?)",
        r"(?:זמין|זמינה|פנוי|פנויה)\s+(?:מ-?|מתאריך|ב)(\S+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1).strip()
            parsed = parse_entry_date(candidate)
            if parsed:
                return parsed
    return parse_entry_date(text)


def extract_apartment(text: str) -> ApartmentExtraction:
    is_listing = passes_keyword_gate(text)
    reasons: list[str] = []

    price = _parse_price(text)
    rooms = _parse_rooms(text)
    sqm = _parse_sqm(text)
    floor = _parse_floor(text)
    brokerage = _parse_brokerage(text)
    city = _find_city(text)
    neighborhood = _find_neighborhood(text)
    entry_date = _find_entry_date(text)
    phones = extract_phone_numbers(text)

    has_balcony = bool(re.search(r"מרפסת", text))
    has_parking = bool(re.search(r"חניה|חנייה", text))
    has_mamad = bool(re.search(r'ממ["״]?ד|ממד', text))
    furnished = bool(re.search(r"מרוהט|מרוהטת", text))
    pets_allowed = bool(re.search(r"חיות|כלב|חתול", text))

    if price:
        reasons.append(f"מחיר: ₪{price:,}")
    if rooms:
        reasons.append(f"{rooms} חדרים")
    if city:
        reasons.append(f"עיר: {city}")
    if brokerage is False:
        reasons.append("ללא תיווך")
    if is_listing:
        reasons.append("מודעת השכרה")

    confidence = 0.5 if is_listing else 0.0
    if price and rooms:
        confidence = 0.8
    if price and rooms and city:
        confidence = 0.9

    return ApartmentExtraction(
        is_listing=is_listing,
        city=city,
        neighborhood=neighborhood,
        price_ils=price,
        rooms=rooms,
        sqm=sqm,
        floor=floor,
        entry_date=entry_date,
        brokerage=brokerage,
        pets_allowed=pets_allowed,
        furnished=furnished,
        has_balcony=has_balcony,
        has_parking=has_parking,
        has_mamad=has_mamad,
        phone_numbers=phones,
        confidence=confidence,
        reasons=reasons,
    )
