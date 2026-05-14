from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """
You are a real-estate listing parser for Israeli Facebook rental groups.
The posts are written in Hebrew. Extract structured information and return valid JSON only.

Rules:
- is_listing: true only if someone is OFFERING an apartment for rent. false if they are SEEKING, selling, or posting something else.
- is_seeking: true if someone is looking for an apartment or a roommate.
- All monetary values in ILS (₪). "אלף" = 1000. "5.5 אלף" = 5500.
- rooms: numeric, e.g. 2, 2.5, 3. "חדר וחצי" = 1.5.
- entry_date: ISO date string YYYY-MM-DD if mentioned, null otherwise. "מיידי"/"מידי" = today's date.
- brokerage: false if "ללא תיווך"/"בלי תיווך", true if "תיווך", null if unknown.
- phone_numbers: list of Israeli phone numbers found in the post, normalized (digits only).
- flags: list of short strings for notable features present in the post (e.g. "מרפסת", "חניה", "ממ\"ד", "מזגן", "מרוהטת", "חיות").
- summary: 1-2 sentence Hebrew summary of the listing for display in Telegram. Only for listings.
- matches_criteria: true/false based on the criteria below.
- skip_reason: short explanation in Hebrew why this post doesn't match, or null if it matches.
"""


def _build_user_prompt(text: str, criteria: dict[str, Any]) -> str:
    preferred_locations = criteria.get("locations", {}).get("preferred", [])
    max_price = criteria.get("price", {}).get("max")
    min_rooms = criteria.get("rooms", {}).get("min")

    criteria_lines = ["Criteria to evaluate matches_criteria:"]
    if preferred_locations:
        criteria_lines.append(f"- Preferred cities/areas: {', '.join(preferred_locations)}")
    if max_price:
        criteria_lines.append(f"- Max price: ₪{max_price}")
    if min_rooms:
        criteria_lines.append(f"- Minimum rooms: {min_rooms}")
    req = criteria.get("require", {})
    for field, val in req.items():
        if val is not None:
            criteria_lines.append(f"- {field} required: {val}")

    criteria_block = "\n".join(criteria_lines)

    return f"""{criteria_block}

Post text:
{text}

Return JSON with these fields:
{{
  "is_listing": bool,
  "is_seeking": bool,
  "city": string|null,
  "neighborhood": string|null,
  "street": string|null,
  "price_ils": int|null,
  "rooms": float|null,
  "sqm": int|null,
  "floor": int|null,
  "entry_date": "YYYY-MM-DD"|null,
  "brokerage": bool|null,
  "pets_allowed": bool|null,
  "furnished": bool|null,
  "has_balcony": bool|null,
  "has_parking": bool|null,
  "has_mamad": bool|null,
  "phone_numbers": [string],
  "flags": [string],
  "summary": string|null,
  "matches_criteria": bool,
  "skip_reason": string|null
}}"""


async def extract_post(text: str, criteria: dict[str, Any], model: str | None = None) -> dict[str, Any] | None:
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping AI extraction")
        return None

    model = model or settings.ai_model
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(text, criteria)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        logger.error("AI extraction failed: %s", e)
        return None
