from __future__ import annotations

from typing import Any

from app.classifier.apartment_rules import ApartmentExtraction


def score_extraction(extraction: ApartmentExtraction, criteria: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = list(extraction.reasons)

    if not extraction.is_listing:
        score -= 40
        reasons.append("לא נראה כמודעת השכרה")
        return score, reasons

    max_price = criteria.get("price", {}).get("max", 9999999)
    if extraction.price_ils:
        if extraction.price_ils <= max_price:
            score += 25
            reasons.append(f"מחיר בטווח (₪{extraction.price_ils:,})")
        else:
            score -= 10
            reasons.append(f"מחיר גבוה מדי (₪{extraction.price_ils:,})")

    preferred_cities = criteria.get("locations", {}).get("preferred", [])
    if extraction.city and extraction.city in preferred_cities:
        score += 20
        reasons.append(f"עיר מועדפת: {extraction.city}")

    preferred_hoods = criteria.get("locations", {}).get("neighborhoods", {}).get("preferred", [])
    if extraction.neighborhood and extraction.neighborhood in preferred_hoods:
        score += 10
        reasons.append(f"שכונה מועדפת: {extraction.neighborhood}")

    min_rooms = criteria.get("rooms", {}).get("min", 0)
    if extraction.rooms is not None:
        if extraction.rooms >= min_rooms:
            score += 15
            reasons.append(f"{extraction.rooms} חדרים — עומד בדרישה מינימלית")
        else:
            score -= 5
            reasons.append(f"פחות מ-{min_rooms} חדרים")

    if extraction.brokerage is False:
        score += 15
        reasons.append("ללא תיווך")

    if extraction.has_balcony:
        score += 5
        reasons.append("מרפסת")
    if extraction.has_parking:
        score += 5
        reasons.append("חניה")
    if extraction.has_mamad:
        score += 5
        reasons.append("ממ\"ד")

    return max(0, score), reasons


ALERT_THRESHOLD = 75
DIGEST_THRESHOLD = 50
