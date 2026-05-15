from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.facebook.models import RawPost
from app.storage.schema import (
    FacebookGroup,
    FacebookPost,
    FacebookPostImage,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def upsert_group(session: Session, group_cfg: dict) -> FacebookGroup:
    # Match by URL first — survives ID renames in groups.yaml
    existing = (
        session.query(FacebookGroup)
        .filter(FacebookGroup.url == group_cfg["url"])
        .first()
    )
    if not existing:
        existing = session.get(FacebookGroup, group_cfg["id"])
    if existing:
        existing.name = group_cfg["name"]
        existing.url = group_cfg["url"]
        existing.enabled = group_cfg.get("enabled", True)
        return existing
    group = FacebookGroup(
        id=group_cfg["id"],
        name=group_cfg["name"],
        url=group_cfg["url"],
        enabled=group_cfg.get("enabled", True),
    )
    session.add(group)
    return group


def get_seen_hashes(session: Session, group_id: str) -> set[str]:
    """Return content hashes of posts that have already been alerted.
    Posts saved but not alerted (e.g. send failed) can be retried."""
    rows = (
        session.query(FacebookPost.content_hash)
        .filter(
            FacebookPost.group_id == group_id,
            FacebookPost.alert_sent_at.isnot(None),
        )
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
        if existing.alert_sent_at is None:
            return existing  # unsent — allow retry
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

    return post


def mark_post_alerted(session: Session, post_id: int) -> None:
    post = session.get(FacebookPost, post_id)
    if post:
        post.alert_sent_at = datetime.now(tz=timezone.utc)


def get_unsent_posts(session: Session, before: datetime) -> list[tuple[FacebookPost, str]]:
    """Return (post, group_name) pairs scraped before this run but never alerted."""
    rows = (
        session.query(FacebookPost, FacebookGroup.name)
        .join(FacebookGroup, FacebookPost.group_id == FacebookGroup.id)
        .filter(
            FacebookPost.alert_sent_at.is_(None),
            FacebookPost.scraped_at < before,
        )
        .all()
    )
    return [(post, group_name) for post, group_name in rows]
