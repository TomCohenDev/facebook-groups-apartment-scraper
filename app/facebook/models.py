from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawImage:
    image_url: str
    alt_text: str = ""
    local_path: str | None = None
    perceptual_hash: str | None = None


@dataclass
class RawComment:
    author_name: str
    author_profile_url: str
    raw_text: str
    timestamp_text: str
    comment_url: str | None = None
    content_hash: str | None = None


@dataclass
class RawPost:
    group_id: str
    raw_text: str
    normalized_text: str
    content_hash: str
    post_url: str | None = None
    external_post_id: str | None = None
    author_name: str | None = None
    author_profile_url: str | None = None
    timestamp_text: str | None = None
    images: list[RawImage] = field(default_factory=list)
    comments: list[RawComment] = field(default_factory=list)
    html_snapshot_path: str | None = None
    screenshot_path: str | None = None
    scraped_at: datetime | None = None


@dataclass
class RunReport:
    group_id: str
    started_at: str
    finished_at: str | None = None
    success: bool = False
    posts_seen: int = 0
    posts_new: int = 0
    comments_scraped: int = 0
    images_found: int = 0
    errors: list[str] = field(default_factory=list)
