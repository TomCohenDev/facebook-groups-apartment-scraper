from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FacebookGroup(Base):
    __tablename__ = "facebook_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    posts: Mapped[list["FacebookPost"]] = relationship(back_populates="group")


class FacebookPost(Base):
    __tablename__ = "facebook_posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("facebook_groups.id"), nullable=True)
    post_url: Mapped[str | None] = mapped_column(Text)
    external_post_id: Mapped[str | None] = mapped_column(String(64))
    author_name: Mapped[str | None] = mapped_column(Text)
    author_profile_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    timestamp_text: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column()
    scraped_at: Mapped[datetime] = mapped_column(default=func.now())
    first_seen_at: Mapped[datetime] = mapped_column(default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(default=func.now())
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    html_snapshot_path: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    alert_sent_at: Mapped[datetime | None] = mapped_column()

    group: Mapped["FacebookGroup"] = relationship(back_populates="posts")
    images: Mapped[list["FacebookPostImage"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[list["FacebookPostComment"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    candidate: Mapped["ApartmentCandidate | None"] = relationship(back_populates="post", cascade="all, delete-orphan")


class FacebookPostImage(Base):
    __tablename__ = "facebook_post_images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("facebook_posts.id", ondelete="CASCADE"), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    post: Mapped["FacebookPost"] = relationship(back_populates="images")


class FacebookPostComment(Base):
    __tablename__ = "facebook_post_comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("facebook_posts.id", ondelete="CASCADE"), nullable=True)
    author_name: Mapped[str | None] = mapped_column(Text)
    author_profile_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    timestamp_text: Mapped[str | None] = mapped_column(Text)
    comment_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scraped_at: Mapped[datetime] = mapped_column(default=func.now())

    post: Mapped["FacebookPost"] = relationship(back_populates="comments")


class ApartmentCandidate(Base):
    __tablename__ = "apartment_candidates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("facebook_posts.id", ondelete="CASCADE"), nullable=True)
    is_listing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    price_ils: Mapped[int | None] = mapped_column(Integer)
    rooms: Mapped[float | None] = mapped_column(Numeric(3, 1))
    sqm: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[int | None] = mapped_column(Integer)
    entry_date = mapped_column(Date, nullable=True)
    brokerage: Mapped[bool | None] = mapped_column(Boolean)
    pets_allowed: Mapped[bool | None] = mapped_column(Boolean)
    furnished: Mapped[bool | None] = mapped_column(Boolean)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean)
    has_parking: Mapped[bool | None] = mapped_column(Boolean)
    has_mamad: Mapped[bool | None] = mapped_column(Boolean)
    phone_numbers = mapped_column(ARRAY(Text), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer)
    reasons = mapped_column(JSON, nullable=True)
    extraction_json = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    alert_sent_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    post: Mapped["FacebookPost"] = relationship(back_populates="candidate")


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
