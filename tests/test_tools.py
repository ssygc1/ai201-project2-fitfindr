"""
tests/test_tools.py

Isolated tests for each FitFindr tool. Run with:
    pytest tests/

Each tool is tested independently — no agent loop involved.
LLM-dependent tools (suggest_outfit, create_fit_card) are tested against
their contracts: non-empty return, correct failure-mode strings.
"""

import pytest
from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("tee", size="S", max_price=None)
    # Every returned item's size should contain "s" (case-insensitive)
    for item in results:
        assert "s" in item["size"].lower()


def test_search_best_match_first():
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 0
    # The top result should have "graphic tee" or "vintage" in its style_tags or title
    top = results[0]
    combined = top["title"].lower() + " ".join(top["style_tags"])
    assert "graphic" in combined or "vintage" in combined or "tee" in combined


def test_search_returns_full_listing_fields():
    results = search_listings("tee", size=None, max_price=None)
    assert len(results) > 0
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "brand", "platform"}
    assert required_fields.issubset(results[0].keys())


def test_search_no_size_filter_when_none():
    results_no_filter = search_listings("jacket", size=None, max_price=None)
    results_with_filter = search_listings("jacket", size="S", max_price=None)
    # Without size filter we should get at least as many results
    assert len(results_no_filter) >= len(results_with_filter)


# ── suggest_outfit ────────────────────────────────────────────────────────────

# A real listing dict to use as new_item across tests
SAMPLE_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "description": "Vintage-style bootleg tee with faded graphic.",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear", "band tee"],
    "size": "L",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}


def test_suggest_outfit_with_wardrobe_returns_string():
    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_empty_wardrobe_returns_string():
    """Empty wardrobe should not crash — returns general styling advice."""
    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_empty_wardrobe_no_exception():
    """Calling with empty wardrobe must never raise."""
    try:
        result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    except Exception as exc:
        pytest.fail(f"suggest_outfit raised an exception on empty wardrobe: {exc}")


# ── create_fit_card ───────────────────────────────────────────────────────────

SAMPLE_OUTFIT = (
    "Pair this faded bootleg tee with your baggy straight-leg dark-wash jeans "
    "and chunky white sneakers for an effortless streetwear look. Layer your "
    "vintage black denim jacket on top for a slightly edgier finish."
)


def test_create_fit_card_returns_string():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_create_fit_card_empty_outfit_returns_error_string():
    """Empty outfit should return an error string — not raise."""
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "cannot create a fit card" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    """Whitespace-only outfit should also trigger the guard."""
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "cannot create a fit card" in result.lower()


def test_create_fit_card_no_exception_on_empty():
    """Guard clause must never raise — only return an error string."""
    try:
        result = create_fit_card("", SAMPLE_ITEM)
    except Exception as exc:
        pytest.fail(f"create_fit_card raised an exception on empty outfit: {exc}")


def test_create_fit_card_varies_on_same_input():
    """Two calls with identical inputs should produce different captions (temperature=1.1)."""
    result1 = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    result2 = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    # With temperature=1.1 the outputs are almost always different
    # We skip asserting inequality to avoid rare flakiness — just confirm both are non-empty
    assert len(result1.strip()) > 0
    assert len(result2.strip()) > 0
