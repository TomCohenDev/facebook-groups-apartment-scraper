from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.facebook.models import RawPost
from app.storage.schema import (
    ApartmentCandidate,
    FacebookGroup,
    FacebookPost,
    FacebookPostComment,
    FacebookPostImage,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def upsert_group(session: Session, group_cfg: dict) -> FacebookGroup:
    existing = session.get(FacebookGroup, group_cfg["id"])
    if existing:
        existing.name = group_cfg["name"]
        existing.url = group_cfg["url"]
        existing.enabled = group_cfg.get("enabled", True)
        existing.priority = group_cfg.get("priority", "medium")
        return existing
    group = FacebookGroup(
        id=group_cfg["id"],
        name=group_cfg["name"],
        url=group_cfg["url"],
        enabled=group_cfg.get("enabled", True),
        priority=group_cfg.get("priority", "medium"),
    )
    session.add(group)
    return group


def get_seen_hashes(session: Session, group_id: str) -> set[str]:
    rows = (
        session.query(FacebookPost.content_hash)
        .filter(FacebookPost.group_id == group_id)
        .all()
    )
    return {r[0] for r in rows}


def save_post(session: Session, raw: RawPost) -> FacebookPost | None:
    existing = (
        session.query(FacebookPost)
        .filter(FacebookPost.content_hash == raw.content_hash)
        .first()
    )
    if existing:
        existing.last_seen_at = datetime.now(tz=timezone.utc)
        return None

    post = FacebookPost(
        group_id=raw.group_id,
        post_url=raw.post_url,
        external_post_id=raw.external_post_id,
        author_name=raw.author_name,
        author_profile_url=raw.author_profile_url,
        raw_text=raw.raw_text,
        normalized_text=raw.normalized_text,
        timestamp_text=raw.timestamp_text,
        content_hash=raw.content_hash,
        scraped_at=raw.scraped_at or datetime.now(tz=timezone.utc),
        html_snapshot_path=raw.html_snapshot_path,
        screenshot_path=raw.screenshot_path,
    )
    session.add(post)
    session.flush()

    for img in raw.images:
        session.add(
            FacebookPostImage(
                post_id=post.id,
                image_url=img.image_url,
                alt_text=img.alt_text,
                local_path=img.local_path,
                perceptual_hash=img.perceptual_hash,
            )
        )

    for cmt in raw.comments:
        existing_cmt = (
            session.query(FacebookPostComment)
            .filter(FacebookPostComment.content_hash == cmt.content_hash)
            .first()
        )
        if not existing_cmt:
            session.add(
                FacebookPostComment(
                    post_id=post.id,
                    author_name=cmt.author_name,
                    author_profile_url=cmt.author_profile_url,
                    raw_text=cmt.raw_text,
                    normalized_text=cmt.raw_text,
                    timestamp_text=cmt.timestamp_text,
                    comment_url=cmt.comment_url,
                    content_hash=cmt.content_hash,
                )
            )

    return post


def save_candidate(
    session: Session,
    post_id: int,
    extraction,
    score: int,
    reasons: list[str],
) -> ApartmentCandidate:
    candidate = ApartmentCandidate(
        post_id=post_id,
        is_listing=extraction.is_listing,
        city=extraction.city,
        neighborhood=extraction.neighborhood,
        street=extraction.street,
        price_ils=extraction.price_ils,
        rooms=float(extraction.rooms) if extraction.rooms else None,
        sqm=extraction.sqm,
        floor=extraction.floor,
        entry_date=extraction.entry_date,
        brokerage=extraction.brokerage,
        pets_allowed=extraction.pets_allowed,
        furnished=extraction.furnished,
        has_balcony=extraction.has_balcony,
        has_parking=extraction.has_parking,
        has_mamad=extraction.has_mamad,
        phone_numbers=extraction.phone_numbers or [],
        score=score,
        reasons=reasons,
        extraction_json=extraction.model_dump(mode="json"),
        status="new",
    )
    session.add(candidate)
    session.flush()
    return candidate


def get_unsent_candidates(session: Session, min_score: int) -> list[ApartmentCandidate]:
    return (
        session.query(ApartmentCandidate)
        .filter(
            ApartmentCandidate.score >= min_score,
            ApartmentCandidate.alert_sent_at.is_(None),
            ApartmentCandidate.status == "new",
        )
        .all()
    )


def mark_alert_sent(session: Session, candidate_id: int) -> None:
    candidate = session.get(ApartmentCandidate, candidate_id)
    if candidate:
        candidate.alert_sent_at = datetime.now(tz=timezone.utc)
