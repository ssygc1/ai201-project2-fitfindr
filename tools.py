"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

from utils.data_loader import load_listings

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

        # Filter: size (case-insensitive substring match in both directions)
        if size is not None:
            item_size = item["size"].lower()
            query_size = size.lower()
            if query_size not in item_size and item_size not in query_size:
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

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
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

        if not wardrobe_items:
            prompt = (
                "You are a personal stylist specializing in thrifted and vintage fashion. "
                "A user is considering buying this secondhand item:\n\n"
                f"{item_description}\n\n"
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
                f"{item_description}\n\n"
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
        new_item: The listing dict for the thrifted item.

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

    except Exception as e:
        return (
            f"Fit card generation failed. Here's the outfit suggestion instead:\n{outfit}"
        )
