"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from tools import (
    compare_price,
    create_fit_card,
    get_trend_report,
    load_style_profile,
    save_style_profile,
    search_listings,
    suggest_outfit,
)

_OLLAMA_MODEL = "llama3.1"


def _get_client() -> OpenAI:
    return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "retry_note": None,          # set if search was retried with looser constraints
        "price_comparison": None,    # dict returned by compare_price
        "trend_report": None,        # dict returned by get_trend_report
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Use the LLM to extract structured search parameters from a natural language query.

    Returns a dict with keys:
        description (str): what the user is looking for
        size (str | None): size filter, or null if not specified
        max_price (float | None): price ceiling, or null if not specified

    Falls back to regex extraction if the LLM call fails.
    """
    client = _get_client()

    prompt = (
        "Extract search parameters from this thrift-shopping query. "
        "Return ONLY a JSON object with these exact keys:\n"
        "  description: a short phrase describing what the user wants (str)\n"
        "  size: the size they want, or null if not specified (str or null)\n"
        "  max_price: the maximum price in USD as a number, or null if not specified (number or null)\n\n"
        f'Query: "{query}"\n\n'
        "JSON only — no explanation, no markdown, no code fences."
    )

    try:
        response = client.chat.completions.create(
            model=_OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()
        # Strip accidental markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        return {
            "description": str(parsed.get("description", query)),
            "size": parsed.get("size") or None,
            "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
        }
    except Exception:
        # Regex fallback: extract price ("under $30", "$30") and size ("size M", "size XL")
        price_match = re.search(r"\$(\d+(?:\.\d+)?)", query)
        size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)\b", query, re.IGNORECASE)
        # Strip price/size phrases from description
        description = re.sub(r"under\s+\$\d+|\$\d+|size\s+[A-Za-z0-9/]+", "", query, flags=re.IGNORECASE)
        description = " ".join(description.split())
        return {
            "description": description or query,
            "size": size_match.group(1) if size_match else None,
            "max_price": float(price_match.group(1)) if price_match else None,
        }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session + load persisted style profile
    session = _new_session(query, wardrobe)
    style_profile = load_style_profile()

    # Step 2: Parse query → description, size, max_price
    try:
        session["parsed"] = _parse_query(query)
    except Exception as e:
        session["error"] = (
            f"Could not understand your query. Please describe what you're looking for, "
            f"your size, and a maximum price. (Detail: {e})"
        )
        return session

    parsed = session["parsed"]
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search — with automatic retry fallback on empty results
    session["search_results"] = search_listings(description, size, max_price)

    if not session["search_results"] and size is not None:
        # Retry 1: drop size filter
        session["search_results"] = search_listings(description, None, max_price)
        if session["search_results"]:
            session["retry_note"] = (
                f"No results for size {size} — showing results for any size instead."
            )
            session["parsed"]["size"] = None
            size = None

    if not session["search_results"] and max_price is not None:
        # Retry 2: drop price filter too
        session["search_results"] = search_listings(description, size, None)
        if session["search_results"]:
            note = f"No results under ${max_price:.0f} — showing results at any price instead."
            session["retry_note"] = (
                (session["retry_note"] + " " + note) if session["retry_note"] else note
            )
            session["parsed"]["max_price"] = None

    if not session["search_results"]:
        session["error"] = (
            f"No listings found for '{description}' even after loosening filters. "
            f"Try different keywords."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: Price comparison (stretch)
    session["price_comparison"] = compare_price(session["selected_item"])

    # Step 6: Trend report (stretch) — informs outfit suggestion
    session["trend_report"] = get_trend_report(session["selected_item"]["style_tags"])

    # Step 7: Suggest outfit — pass style profile + trend context
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
        style_profile=style_profile,
        trend_report=session["trend_report"],
    )

    # Step 8: Create fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    # Step 9: Persist style profile for next session (stretch)
    save_style_profile(session["selected_item"])

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_empty_wardrobe, get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        item = session["selected_item"]
        print(f"Parsed: {session['parsed']}")
        print(f"Found:  {item['title']} — ${item['price']} ({item['platform']})")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(f"fit_card is None: {session2['fit_card'] is None}")
    print(f"outfit_suggestion is None: {session2['outfit_suggestion'] is None}")
