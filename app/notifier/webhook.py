from __future__ import annotations

import httpx

from app.storage.schema import ApartmentCandidate, FacebookPost
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def send_webhook(
    url: str,
    candidate: ApartmentCandidate,
    post: FacebookPost,
    group_name: str,
) -> bool:
    payload = {
        "score": candidate.score,
        "city": candidate.city,
        "neighborhood": candidate.neighborhood,
        "price_ils": candidate.price_ils,
        "rooms": float(candidate.rooms) if candidate.rooms else None,
        "entry_date": str(candidate.entry_date) if candidate.entry_date else None,
        "brokerage": candidate.brokerage,
        "post_url": post.post_url,
        "group_name": group_name,
        "reasons": candidate.reasons,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error("Webhook failed: %s", e)
        return False
