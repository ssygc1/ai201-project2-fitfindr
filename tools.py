"""
tools.py

FitFindr tools — required and stretch.

Tools:
    search_listings(description, size, max_price)              → list[dict]
    suggest_outfit(new_item, wardrobe, style_profile, trend)   → str
    create_fit_card(outfit, new_item)                          → str
    compare_price(item)                                        → dict   [stretch]
    get_trend_report(style_tags)                               → dict   [stretch]
    load_style_profile()                                       → dict   [stretch]
    save_style_profile(item)                                   → None   [stretch]
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from utils.data_loader import load_listings

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "data", "style_profile.json")
_TRENDS_PATH = os.path.join(os.path.dirname(__file__), "data", "trends.json")

load_dotenv()

_OLLAMA_MODEL = "llama3.1"


# ── Ollama client ─────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at the local Ollama server."""
    return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Build keyword set from description (lowercase, split on whitespace)
    keywords = set(description.lower().split())

    scored = []
    for item in listings:
        # Filter: price ceiling
        if max_price is not None and item["price"] > max_price:
            continue

        # Filter: size — tokenize on delimiters so "S" doesn't match "XXS"
        if size is not None:
            item_tokens = set(re.split(r"[\s/,()]+", item["size"].lower()))
            if size.lower() not in item_tokens:
                continue

        # Score: count keyword hits across title, description, and style_tags
        searchable = " ".join([
            item["title"].lower(),
            item["description"].lower(),
            " ".join(item["style_tags"]),
        ])
        score = sum(1 for kw in keywords if kw in searchable)

        if score > 0:
            scored.append((score, item))

    # Sort highest score first, then by price ascending as tiebreaker
    scored.sort(key=lambda x: (-x[0], x[1]["price"]))
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(
    new_item: dict,
    wardrobe: dict,
    style_profile: dict | None = None,
    trend_report: dict | None = None,
) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item:      A listing dict (the item the user is considering buying).
        wardrobe:      A wardrobe dict with an 'items' key. May be empty.
        style_profile: Optional dict of stored user style preferences from
                       previous sessions. Used to personalise suggestions.
        trend_report:  Optional dict from get_trend_report(). Trend context is
                       woven into the prompt so suggestions reflect what's current.

    Returns:
        A non-empty string with outfit suggestions.
    """
    try:
        client = _get_client()

        item_description = (
            f"Title: {new_item['title']}\n"
            f"Category: {new_item['category']}\n"
            f"Colors: {', '.join(new_item['colors'])}\n"
            f"Style tags: {', '.join(new_item['style_tags'])}\n"
            f"Condition: {new_item['condition']}\n"
            f"Price: ${new_item['price']}\n"
            f"Platform: {new_item['platform']}"
        )

        wardrobe_items = wardrobe.get("items", [])

        # Build optional context blocks
        profile_block = ""
        if style_profile and style_profile.get("interaction_count", 0) > 0:
            styles = ", ".join(style_profile["preferred_styles"][:6]) or "none yet"
            colors = ", ".join(style_profile["preferred_colors"][:5]) or "none yet"
            profile_block = (
                f"\nThe user's established style preferences (from previous sessions): "
                f"they gravitate toward {styles} styles and tend to wear {colors} colors. "
                f"Factor this in when choosing which wardrobe pieces to suggest.\n"
            )

        trend_block = ""
        if trend_report and trend_report.get("trend_summary"):
            trend_block = f"\nTrend context: {trend_report['trend_summary']}\n"

        if not wardrobe_items:
            prompt = (
                "You are a personal stylist specializing in thrifted and vintage fashion. "
                "A user is considering buying this secondhand item:\n\n"
                f"{item_description}\n"
                f"{profile_block}"
                f"{trend_block}\n"
                "They haven't told you what's in their wardrobe. Give them 1–2 general outfit "
                "ideas that would work well with this piece — describe what types of bottoms, "
                "shoes, and outerwear pair best, and what overall vibe each outfit creates. "
                "Keep it casual and conversational, like advice from a knowledgeable friend."
            )
        else:
            wardrobe_text = "\n".join(
                f"- {w['name']} ({w['category']}, colors: {', '.join(w['colors'])}, "
                f"style: {', '.join(w['style_tags'])})"
                + (f" — {w['notes']}" if w.get("notes") else "")
                for w in wardrobe_items
            )
            prompt = (
                "You are a personal stylist specializing in thrifted and vintage fashion. "
                "A user is considering buying this secondhand item:\n\n"
                f"{item_description}\n"
                f"{profile_block}"
                f"{trend_block}\n"
                "Their current wardrobe contains:\n"
                f"{wardrobe_text}\n\n"
                "Suggest 1–2 complete outfit combinations using the new item and specific "
                "pieces from their wardrobe (refer to wardrobe pieces by name). Describe "
                "the overall vibe of each outfit. Keep it casual and conversational."
            )

        response = client.chat.completions.create(
            model=_OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Could not generate outfit suggestions right now. Try again in a moment. (Error: {e})"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().

        

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    # Guard: empty or whitespace-only outfit
    if not outfit or not outfit.strip():
        return (
            "Cannot create a fit card — outfit suggestion is missing. "
            "Try running the full search again."
        )

    try:
        client = _get_client()

        prompt = (
            "You are writing an Instagram/TikTok OOTD caption for a thrift find. "
            "Write in a casual, authentic first-person voice — like a real person "
            "posting their outfit, not a brand ad or product description. "
            "Keep it 2–4 sentences.\n\n"
            f"The thrifted item: {new_item['title']} — ${new_item['price']} on {new_item['platform']}\n"
            f"The outfit: {outfit}\n\n"
            "Requirements:\n"
            "- Mention the item name, price, and platform exactly once each, naturally\n"
            "- Capture the specific vibe of the outfit (not generic praise)\n"
            "- Sound like something a real person would caption an OOTD post with\n"
            "- No hashtags\n\n"
            "Write only the caption — no intro, no explanation."
        )

        response = client.chat.completions.create(
            model=_OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()

    except Exception:
        return (
            f"Fit card generation failed. Here's the outfit suggestion instead:\n{outfit}"
        )


# ── Tool 4: compare_price (stretch) ──────────────────────────────────────────

def compare_price(item: dict) -> dict:
    """
    Estimate whether the item's price is fair based on comparable listings
    in the dataset (same category + shared style tags).

    Args:
        item: A listing dict to evaluate.

    Returns:
        A dict with keys:
            assessment (str):              "great deal", "fair price", or "above average"
            reasoning (str):               Human-readable explanation with numbers
            avg_comparable_price (float):  Average price of comparable items
            comparable_count (int):        How many listings were used for comparison
    """
    listings = load_listings()
    item_tags = set(item["style_tags"])
    category = item["category"]

    # Prefer: same category + at least one shared style tag
    comparables = [
        l for l in listings
        if l["id"] != item["id"]
        and l["category"] == category
        and set(l["style_tags"]) & item_tags
    ]
    method = "category + style"

    # Fallback: same category only
    if not comparables:
        comparables = [l for l in listings if l["id"] != item["id"] and l["category"] == category]
        method = "category only"

    if not comparables:
        return {
            "assessment": "unknown",
            "reasoning": "Not enough comparable listings in the dataset to assess this price.",
            "avg_comparable_price": None,
            "comparable_count": 0,
        }

    avg = sum(l["price"] for l in comparables) / len(comparables)
    price = item["price"]
    pct_diff = (price - avg) / avg * 100

    if pct_diff <= -20:
        assessment = "great deal"
        reasoning = (
            f"At ${price:.2f}, this is {abs(pct_diff):.0f}% below the average ${avg:.2f} "
            f"across {len(comparables)} comparable {category} listings (matched by {method}). "
            f"Strong buy."
        )
    elif pct_diff <= 10:
        assessment = "fair price"
        reasoning = (
            f"At ${price:.2f}, this is right around the average ${avg:.2f} "
            f"across {len(comparables)} comparable {category} listings (matched by {method}). "
            f"Reasonable."
        )
    else:
        assessment = "above average"
        reasoning = (
            f"At ${price:.2f}, this is {pct_diff:.0f}% above the average ${avg:.2f} "
            f"across {len(comparables)} comparable {category} listings (matched by {method}). "
            f"Worth negotiating if the platform allows offers."
        )

    return {
        "assessment": assessment,
        "reasoning": reasoning,
        "avg_comparable_price": round(avg, 2),
        "comparable_count": len(comparables),
    }


# ── Tool 5: get_trend_report (stretch) ───────────────────────────────────────

def get_trend_report(style_tags: list[str]) -> dict:
    """
    Return trend information relevant to the given style tags, using mock
    trend data that simulates a seasonal fashion platform API response.

    Args:
        style_tags: List of style tag strings from the item being evaluated.

    Returns:
        A dict with keys:
            trending_styles (list[str]):     All currently trending style names
            item_trending_tags (list[str]):  Which of the item's tags are trending
            trend_summary (str):             Human-readable trend context string
            momentum (dict):                 {style: momentum} for trending item tags
    """
    with open(_TRENDS_PATH) as f:
        trends_data = json.load(f)

    trending_map = {t["style"].lower(): t for t in trends_data["trending"]}
    trending_names = list(trending_map.keys())
    item_trending = [tag for tag in style_tags if tag.lower() in trending_map]
    momentum = {tag: trending_map[tag.lower()]["momentum"] for tag in item_trending}
    season_note = trends_data.get("season_note", "")

    if item_trending:
        rising = [t for t in item_trending if momentum[t] == "rising"]
        peak = [t for t in item_trending if momentum[t] == "peak"]
        trend_parts = []
        if rising:
            trend_parts.append(f"{', '.join(rising)} (rising)")
        if peak:
            trend_parts.append(f"{', '.join(peak)} (at peak)")
        summary = (
            f"This item's style is on-trend right now — {' and '.join(trend_parts)} "
            f"for {trends_data.get('season', 'this season')}. {season_note}"
        )
    else:
        closest = [t["style"] for t in trends_data["trending"] if t["momentum"] in ("rising", "peak")][:3]
        summary = (
            f"This item's specific styles aren't in the current trend cycle. "
            f"What's moving right now: {', '.join(closest)}. {season_note}"
        )

    return {
        "trending_styles": trending_names,
        "item_trending_tags": item_trending,
        "trend_summary": summary,
        "momentum": momentum,
    }


# ── Style Profile Memory (stretch) ───────────────────────────────────────────

def load_style_profile() -> dict:
    """
    Load the user's persisted style profile from disk.

    Returns:
        A dict with keys:
            preferred_styles (list[str]):     Style tags accumulated across sessions
            preferred_colors (list[str]):     Colors accumulated across sessions
            preferred_categories (list[str]): Item categories the user has engaged with
            interaction_count (int):          Total completed interactions
    """
    if os.path.exists(_PROFILE_PATH):
        with open(_PROFILE_PATH) as f:
            return json.load(f)
    return {
        "preferred_styles": [],
        "preferred_colors": [],
        "preferred_categories": [],
        "interaction_count": 0,
    }


def save_style_profile(item: dict) -> None:
    """
    Update and persist the style profile based on the item the user engaged with.
    Accumulates style_tags, colors, and category from the selected listing.

    Args:
        item: The selected listing dict from the completed interaction.
    """
    profile = load_style_profile()

    for tag in item.get("style_tags", []):
        if tag not in profile["preferred_styles"]:
            profile["preferred_styles"].append(tag)

    for color in item.get("colors", []):
        if color not in profile["preferred_colors"]:
            profile["preferred_colors"].append(color)

    category = item.get("category")
    if category and category not in profile["preferred_categories"]:
        profile["preferred_categories"].append(category)

    profile["interaction_count"] += 1

    with open(_PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)
