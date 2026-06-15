# FitFindr

A multi-tool AI agent that helps you find secondhand pieces and figure out how to wear them. Describe what you're looking for, and FitFindr searches mock thrift listings, suggests outfits using your existing wardrobe, and writes a shareable caption — all in one flow.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install openai
```

This project uses [Ollama](https://ollama.com) for local LLM inference — no API key required.

```bash
# Install Ollama, then pull the model
ollama pull llama3.1
```

Run the app:

```bash
python app.py
# Open http://localhost:7860
```

Run the CLI test (both happy path and no-results path):

```bash
python agent.py
```

Run the test suite:

```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the mock listings dataset for secondhand items matching the user's description, optional size filter, and optional price ceiling.

**Inputs:**
- `description` (str) — Natural-language keywords describing what the user wants (e.g., `"vintage graphic tee"`). Scored against each listing's title, description text, and style_tags.
- `size` (str | None) — Size string to filter by (e.g., `"M"`, `"W28"`). Case-insensitive substring match so `"M"` matches `"S/M"`. Pass `None` to skip size filtering.
- `max_price` (float | None) — Maximum price in USD (inclusive). Pass `None` to skip price filtering.

**Output:** A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns an empty list when nothing matches — never raises an exception.

**Failure mode:** Returns `[]`. The agent detects this, sets a specific error message naming the filters used, and exits early without calling the other tools.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Uses the LLM to suggest 1–2 complete outfit combinations that pair the thrifted item with pieces the user already owns.

**Inputs:**
- `new_item` (dict) — A single listing dict from `search_listings`. Used fields: `title`, `category`, `colors`, `style_tags`, `condition`, `price`, `platform`.
- `wardrobe` (dict) — A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each item has `name`, `category`, `colors` (list), `style_tags` (list), `notes`. The list may be empty.

**Output:** A non-empty string. When the wardrobe has items, the response names specific pieces by name. When the wardrobe is empty, it gives general styling advice (silhouettes, colors, shoe types that work with the item) instead of crashing.

**Failure mode:** If the LLM call raises an exception, returns `"Could not generate outfit suggestions right now. Try again in a moment."` — the agent stores this string and continues to `create_fit_card`.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Generates a 2–4 sentence casual outfit caption — the kind someone would post as an Instagram OOTD — from the outfit suggestion and the thrifted item's details.

**Inputs:**
- `outfit` (str) — The outfit suggestion string from `suggest_outfit`. Must be non-empty.
- `new_item` (dict) — The listing dict for the thrifted item. Used to naturally weave in the item name, price, and platform.

**Output:** A 2–4 sentence string in casual first-person social media tone. Mentions the item name, price, and platform exactly once each. Generated at temperature 1.1 so each call produces a different caption.

**Failure mode:** If `outfit` is empty or whitespace-only, immediately returns `"Cannot create a fit card — outfit suggestion is missing. Try running the full search again."` without calling the LLM.

---

## Planning Loop

The planning loop runs as a sequence of conditional checks inside `run_agent()`. Each step only proceeds if the previous one succeeded — the agent does not call all three tools unconditionally.

**Step 1 — Parse the query.**
The LLM extracts `{description, size, max_price}` as structured JSON from the natural-language query. If the LLM fails (e.g., Ollama not running), a regex fallback extracts price (`$30`) and size (`size M`) patterns directly from the query text.

**Step 2 — Search.**
`search_listings(description, size, max_price)` runs with the parsed parameters.

- **If results is empty:** The agent sets `session["error"]` to a message naming the filters used and suggesting what to change (e.g., "Try: remove the size filter, or raise your budget, or use broader keywords."). Returns the session immediately. `suggest_outfit` and `create_fit_card` are never called.
- **If results is non-empty:** Sets `session["selected_item"] = results[0]`. Continues to step 3.

**Step 3 — Suggest outfit.**
`suggest_outfit(selected_item, wardrobe)` always returns a non-empty string (it handles its own failures internally). No early-exit check needed.

**Step 4 — Create fit card.**
`create_fit_card(outfit_suggestion, selected_item)` always returns a string. Result stored in `session["fit_card"]`.

**Step 5 — Return session.**
`session["error"]` is `None`. The caller reads `fit_card` and `outfit_suggestion` for display.

The agent's behavior is visibly different for a no-results query (stops at step 2, returns error) versus a successful query (runs all four steps).

---

## State Management

All state lives in a single Python dict (`session`) created by `_new_session()` at the start of each `run_agent()` call. It is the single source of truth for the entire interaction — no global variables, no files, no re-prompting the user.

| Key | Type | Set when | Read by |
|-----|------|----------|---------|
| `query` | str | Initialization | Error messages |
| `parsed` | dict `{description, size, max_price}` | After query parsing | Passed as args to `search_listings` |
| `search_results` | list[dict] | After `search_listings` | Checked for emptiness; first item selected |
| `selected_item` | dict | After non-empty results | Passed to `suggest_outfit` and `create_fit_card` |
| `wardrobe` | dict | Initialization (from caller) | Passed to `suggest_outfit` |
| `outfit_suggestion` | str | After `suggest_outfit` | Passed to `create_fit_card` |
| `fit_card` | str | After `create_fit_card` | Returned to UI |
| `error` | str or None | On early-exit failure | Checked by caller before reading outputs |

The item found by `search_listings` is stored as `session["selected_item"]` and passed directly into `suggest_outfit` — the user never re-enters it. The outfit string from `suggest_outfit` is stored as `session["outfit_suggestion"]` and passed directly into `create_fit_card`.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match (empty list) | Sets `session["error"]` = specific message with filters used + retry suggestions. Returns early — `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | Wardrobe is empty | Detects `wardrobe["items"] == []` before calling LLM. Switches to a general-styling prompt. Returns a non-empty string — no exception. |
| `suggest_outfit` | LLM API call fails (exception) | Catches exception, returns `"Could not generate outfit suggestions right now. Try again in a moment."` Agent stores this and continues. |
| `create_fit_card` | `outfit` is empty/whitespace | Guard clause at top of function. Returns `"Cannot create a fit card — outfit suggestion is missing."` without calling the LLM. |
| `create_fit_card` | LLM API call fails (exception) | Returns `"Fit card generation failed. Here's the outfit suggestion instead: [outfit]"` |

**Concrete example from testing (no-results path):**

Query: `"designer ballgown size XXS under $5"`

```
Error: No listings found for 'designer ballgown' with size XXS and under $5.
Try: remove the size filter, or raise your budget, or use broader keywords.
```

`session["fit_card"]` and `session["outfit_suggestion"]` remain `None`. The agent does not call `suggest_outfit` or `create_fit_card`. Confirmed by `python agent.py`.

---

## Spec Reflection

**One way the spec helped:**
Writing the planning loop section of `planning.md` with explicit conditional branches ("if `search_results` is empty, set error and return — do NOT proceed") made it impossible to accidentally write a loop that calls all three tools unconditionally. The spec forced me to think about the no-results path before writing any code, which meant the early-exit logic was built in from the start rather than added as an afterthought.

**One divergence and why:**
The spec assumed Groq as the LLM provider. During implementation the Groq API key was invalid, so I switched to Ollama (local, OpenAI-compatible). Because the code used the OpenAI-compatible interface pattern throughout, the actual change was minimal: swap `from groq import Groq` for `from openai import OpenAI`, point `base_url` at `http://localhost:11434/v1`, and change the model name from `llama-3.3-70b-versatile` to `llama3.1`. No tool logic changed. The `_get_client()` helper function isolated the provider detail so it only needed to change in one place per file.

---

## AI Usage

**Instance 1 — Implementing the planning loop**

I gave Claude the Architecture diagram from `planning.md` (the full ASCII flowchart showing the conditional branch at step 3) and the Planning Loop and State Management sections. I asked it to implement `run_agent()` in `agent.py` following those conditional branches exactly and storing each result in the session dict keys defined in `_new_session()`.

What I reviewed and changed: The generated code initially called `search_listings` without using the parsed `size` and `max_price` — it passed the raw query string instead of the structured params. I caught this by comparing the function call against the `session["parsed"]` dict structure in my spec. I also added the regex fallback in `_parse_query()` myself after testing showed the LLM parser could fail silently.

**Instance 2 — Implementing `suggest_outfit` and `create_fit_card`**

I gave Claude the Tool 2 and Tool 3 spec blocks from `planning.md` (inputs with types, return values, failure modes) plus the wardrobe schema JSON so it understood the dict structure. I asked it to implement each function using the Groq client already in `tools.py`, with the empty-wardrobe branch for Tool 2 and the guard clause for Tool 3.

What I reviewed and changed: The generated `create_fit_card` used `temperature=0.7`, which produced nearly identical captions on repeated calls. I changed it to `temperature=1.1` per my spec requirement that outputs vary. I also verified that the empty-outfit guard in `create_fit_card` returned a string (not raised an exception) by running `pytest tests/` — the test `test_create_fit_card_empty_outfit_returns_error_string` confirmed this before I moved on.
