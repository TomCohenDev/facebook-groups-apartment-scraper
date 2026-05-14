"""
Discover Facebook group IDs and names from search pages.

Navigates to Facebook group search URLs, intercepts the GraphQL responses
that carry group cards, and extracts name + numeric ID.

Usage:
    python scripts/find_groups.py                  # uses SEARCH_QUERIES below
    python scripts/find_groups.py --output groups_found.yaml

Edit SEARCH_QUERIES to add / remove keywords.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser.context import create_context
from app.browser.login_check import assert_logged_in
from app.settings import settings
from app.utils.logging import get_logger, setup_logging

setup_logging("INFO")
logger = get_logger(__name__)

# ── Edit these to control what gets searched ───────────────────────────────────
SEARCH_QUERIES = [
    "דירות להשכרה בהוד השרון כפס ורעננה",
    "יחידות דיור דירות ללא תיווך כפר סבא הוד השרון",
    "דירות להשכרה בין חברים הוד השרון כפס רעננה",
    "דירות להשכרה בהרצליה רעננה כפר סבא רמת השרון הוד השרון",
    "יחידות דירות להשכרה בשרון",
    "דירות מפה לאוזן כפר סבא רעננה הוד השרון",
    "להשכרה במושבים וקיבוצים",
    "דירות בקיבוצים ומושבים מרכז והשרון",
    "דירות להשכרה בכפר סבא והסביבה",
    "דירות להשכרה בכפר סבא",
    "דירות להשכרה ברעננה",
    "דירות להשכרה בהוד השרון",
    "דירות בכפר סבא רעננה והוד השרון",
    "דירות להשכרה אזור השרון במחיר הוגן",
    "דירות להשכרה מושבים שרון",
    "מושבי השרון",
    "השכרה בהוד השרון",
    "השכרה בכפר סבא",
    "השכרה ברעננה",
    "השכרה בנווה ירק",
    "השכרה בנווה נאמן",
    "השכרה בגני עם",
    "השכרה בנווה הדר",
    "השכרה בכפר מל\"ל",
]

# ── Known groups with direct URLs (skip search for these) ─────────────────────
KNOWN_GROUPS = [
    ("דירות להשכרה בהוד השרון כפ״ס ורעננה", "https://www.facebook.com/groups/234893187572065/"),
    ("יחידות דיור/דירות ללא תיווך בכפר סבא הוד השרון והמושבים", "https://www.facebook.com/groups/1012473358783684/"),
    ("דירות להשכרה בין חברים - הוד השרון כפס רעננה", "https://www.facebook.com/groups/188200278254717/"),
    ("דירות להשכרה בהרצליה רעננה כפר סבא רמת השרון והוד השרון", "https://www.facebook.com/groups/dirotlehascarabeherzelia/"),
    ("יחידות / דירות להשכרה בשרון", "https://www.facebook.com/groups/1121067317909873/"),
    ("דירות מפה לאוזן בכפר סבא רעננה והוד השרון", "https://www.facebook.com/groups/1185463971546919/"),
    ("להשכרה במושבים וקיבוצים", "https://www.facebook.com/groups/1905601096374544/"),
    ("דירות בקיבוצים ומושבים מרכז והשרון", "https://www.facebook.com/groups/512846588904138/"),
    ("דירות להשכרה בהוד השרון", "https://www.facebook.com/groups/850386785010659/"),
    ("פורום תושבים ברעננה", "https://www.facebook.com/groups/raananim/"),
]

_GROUP_ID_RE = re.compile(r"facebook\.com/groups/([^/?&#]+)")


def _url_to_id_slug(url: str) -> str:
    m = _GROUP_ID_RE.search(url)
    return m.group(1).rstrip("/") if m else ""


def _slug_to_yaml_id(slug: str) -> str:
    slug = re.sub(r"[^\w]", "_", slug).strip("_").lower()
    return slug[:40]


def _extract_groups_from_json(data) -> list[tuple[str, str]]:
    """Recursively walk a JSON blob and pull out group {name, id} pairs."""
    results: list[tuple[str, str]] = []
    if isinstance(data, dict):
        # Facebook GraphQL group node
        node_type = data.get("__typename", "")
        if node_type == "Group" or ("group_id" in data and "name" in data):
            gid = str(data.get("group_id") or data.get("id") or "")
            name = data.get("name", "")
            if gid and name and gid.isdigit():
                results.append((name, gid))
        # also check edges/nodes pattern
        for val in data.values():
            results.extend(_extract_groups_from_json(val))
    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_groups_from_json(item))
    return results


async def scrape_search_page(page, query: str) -> list[tuple[str, str]]:
    """Return list of (name, group_id_or_slug) found for a search query."""
    url = f"https://www.facebook.com/search/groups/?q={quote(query)}"
    found: list[tuple[str, str]] = []
    intercepted: list[tuple[str, str]] = []

    async def handle_response(response):
        try:
            if "graphql" not in response.url and "api/graphql" not in response.url:
                return
            if response.status != 200:
                return
            text = await response.text()
            # FB sometimes returns multiple JSON objects separated by newlines
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    pairs = _extract_groups_from_json(data)
                    intercepted.extend(pairs)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    page.on("response", handle_response)

    logger.info("Searching: %s", query)
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(5)

    # scroll a bit to load more results
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(2)

    # DOM fallback: pick up any group hrefs visible on the page
    dom_links: list[str] = []
    try:
        anchors = page.locator("a[href*='/groups/']")
        count = await anchors.count()
        for i in range(count):
            href = await anchors.nth(i).get_attribute("href") or ""
            if "/groups/" in href:
                dom_links.append(href)
    except Exception:
        pass

    for href in dom_links:
        slug = _url_to_id_slug(href)
        if slug and slug not in ("", "feed", "discover", "search"):
            # try to find a nearby name in the DOM
            found.append(("", slug))

    # Prefer intercepted (has real name + numeric id)
    if intercepted:
        logger.info("  → %d groups from network interception", len(intercepted))
        return intercepted

    logger.info("  → %d group links from DOM", len(found))
    return found


def _build_yaml_entry(name: str, id_or_slug: str, idx: int) -> dict:
    if id_or_slug.isdigit():
        url = f"https://www.facebook.com/groups/{id_or_slug}/"
    else:
        url = f"https://www.facebook.com/groups/{id_or_slug}/"
    yaml_id = _slug_to_yaml_id(id_or_slug) or f"group_{idx}"
    return {
        "id": yaml_id,
        "name": name or yaml_id,
        "url": url,
        "enabled": False,   # review before enabling
        "max_posts_per_run": 20,
        "scrape_comments": False,
        "max_comments_per_post": 0,
        "scrape_images": True,
    }


async def main(output: str) -> None:
    seen_ids: set[str] = set()
    groups: list[dict] = []

    # Add known groups first
    for idx, (name, url) in enumerate(KNOWN_GROUPS):
        slug = _url_to_id_slug(url)
        if slug and slug not in seen_ids:
            seen_ids.add(slug)
            groups.append(_build_yaml_entry(name, slug, idx))

    # Scrape search pages
    playwright, context = await create_context(settings.fb_profile_dir, headless=False)
    try:
        await assert_logged_in(context)
        page = await context.new_page()

        for idx, query in enumerate(SEARCH_QUERIES):
            try:
                results = await scrape_search_page(page, query)
                for name, gid in results:
                    if gid and gid not in seen_ids:
                        seen_ids.add(gid)
                        groups.append(_build_yaml_entry(name, gid, len(groups)))
            except Exception as e:
                logger.warning("Query failed (%s): %s", query, e)

        await page.close()
    finally:
        await context.close()
        await playwright.stop()

    # Output
    output_data = {"groups": groups}
    out_path = Path(output)
    out_path.write_text(
        yaml.dump(output_data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Wrote %d groups to %s", len(groups), out_path)
    print(f"\n✅ Found {len(groups)} groups → {out_path}")
    print("Review the file, set enabled: true for the ones you want, then copy into config/groups.yaml")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="groups_found.yaml")
    args = parser.parse_args()
    asyncio.run(main(args.output))
