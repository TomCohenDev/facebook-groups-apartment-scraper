"""Merge groups_found.yaml into config/groups.yaml (dedupe by canonical URL)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def norm_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    u = u.split("?")[0].split("#")[0].rstrip("/")
    return u.lower() + "/"


def slug_from_url(u: str) -> str:
    m = re.search(r"/groups/([^/?#]+)", u, re.I)
    return (m.group(1).rstrip("/") if m else "").strip()


def canonical_url(u: str) -> str:
    u = (u or "").strip().split("?")[0].split("#")[0].rstrip("/")
    return u + "/"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config" / "groups.yaml"
    found_path = root / "groups_found.yaml"

    with cfg_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with found_path.open(encoding="utf-8") as f:
        found = yaml.safe_load(f)

    existing = cfg.get("groups") or []
    found_groups = found.get("groups") or []

    seen_urls = {norm_url(g["url"]) for g in existing if g.get("url")}
    used_ids = {g["id"] for g in existing if g.get("id")}

    defaults = {
        "enabled": True,
        "max_posts_per_run": 20,
        "scrape_comments": True,
        "max_comments_per_post": 5,
        "scrape_images": True,
    }

    added: list[dict] = []
    skipped_dup = 0

    for g in found_groups:
        url = g.get("url") or ""
        nu = norm_url(url)
        if not nu or nu in seen_urls:
            skipped_dup += 1
            continue
        seen_urls.add(nu)

        slug = slug_from_url(url)
        if slug.isdigit():
            cand = f"fb_{slug}"
        else:
            cand = re.sub(r"[^0-9a-zA-Z_]", "_", slug).strip("_").lower()[:80] or "group"

        yaml_id = cand
        n = 2
        while yaml_id in used_ids:
            yaml_id = f"{cand}_{n}"
            n += 1
        used_ids.add(yaml_id)

        name = g.get("name") or slug or yaml_id
        added.append(
            {
                "id": yaml_id,
                "name": name,
                "url": canonical_url(url),
                **defaults,
            }
        )

    merged = existing + added

    text = yaml.safe_dump(
        {"groups": merged},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    cfg_path.write_text(text, encoding="utf-8")

    print(
        f"Existing: {len(existing)}, found file: {len(found_groups)}, "
        f"appended new: {len(added)}, skipped (dup URL): {skipped_dup}, total: {len(merged)}"
    )


if __name__ == "__main__":
    main()
