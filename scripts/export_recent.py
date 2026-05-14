"""
Export recently seen apartment candidates.

Usage:
    python scripts/export_recent.py --hours 24 --format json
    python scripts/export_recent.py --hours 48 --format csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.db import SessionLocal
from app.storage.schema import ApartmentCandidate, FacebookPost


def main(hours: int, fmt: str) -> None:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)

    with SessionLocal() as session:
        candidates = (
            session.query(ApartmentCandidate)
            .filter(ApartmentCandidate.created_at >= cutoff)
            .order_by(ApartmentCandidate.score.desc())
            .all()
        )

        rows = []
        for c in candidates:
            post = session.get(FacebookPost, c.post_id)
            rows.append(
                {
                    "score": c.score,
                    "city": c.city,
                    "neighborhood": c.neighborhood,
                    "price_ils": c.price_ils,
                    "rooms": float(c.rooms) if c.rooms else None,
                    "sqm": c.sqm,
                    "brokerage": c.brokerage,
                    "entry_date": str(c.entry_date) if c.entry_date else None,
                    "post_url": post.post_url if post else None,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )

    if fmt == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif fmt == "csv":
        if not rows:
            print("No results.")
            return
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        print(buf.getvalue())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--format", dest="fmt", default="json", choices=["json", "csv"])
    args = parser.parse_args()
    main(args.hours, args.fmt)
