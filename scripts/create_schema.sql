-- Run this in Supabase: Dashboard > SQL Editor > New query
-- Alternatively, python -m app.main will call create_tables() automatically via SQLAlchemy.

create table if not exists facebook_groups (
  id text primary key,
  name text not null,
  url text not null unique,
  enabled boolean not null default true,
  priority text not null default 'medium',
  created_at timestamptz not null default now()
);

create table if not exists facebook_posts (
  id bigserial primary key,
  group_id text references facebook_groups(id),
  post_url text,
  external_post_id text,
  author_name text,
  author_profile_url text,
  raw_text text,
  normalized_text text,
  timestamp_text text,
  posted_at timestamptz,
  scraped_at timestamptz not null default now(),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  content_hash text not null unique,
  html_snapshot_path text,
  screenshot_path text
);

create table if not exists facebook_post_images (
  id bigserial primary key,
  post_id bigint references facebook_posts(id) on delete cascade,
  image_url text,
  local_path text,
  alt_text text,
  perceptual_hash text,
  created_at timestamptz not null default now()
);

create table if not exists facebook_post_comments (
  id bigserial primary key,
  post_id bigint references facebook_posts(id) on delete cascade,
  author_name text,
  author_profile_url text,
  raw_text text,
  normalized_text text,
  timestamp_text text,
  comment_url text,
  content_hash text not null unique,
  scraped_at timestamptz not null default now()
);

create table if not exists apartment_candidates (
  id bigserial primary key,
  post_id bigint references facebook_posts(id) on delete cascade,
  is_listing boolean not null,
  city text,
  neighborhood text,
  street text,
  price_ils integer,
  rooms numeric(3,1),
  sqm integer,
  floor integer,
  entry_date date,
  brokerage boolean,
  pets_allowed boolean,
  furnished boolean,
  has_balcony boolean,
  has_parking boolean,
  has_mamad boolean,
  phone_numbers text[],
  score integer,
  reasons jsonb,
  extraction_json jsonb,
  status text not null default 'new',
  alert_sent_at timestamptz,
  created_at timestamptz not null default now()
);
