# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items that match the user's description keywords, optional size, and optional price ceiling. Returns a ranked list of matching listings so the agent can pick the best result to pass forward.

**Input parameters:**
- `description` (str): Natural-language keywords describing what the user is looking for (e.g., "vintage graphic tee", "floral midi skirt"). Used to score each listing by keyword overlap against its title, description, and style_tags fields.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M", "W28"). Matching is case-insensitive and substring-based so "M" matches "S/M". Pass None to skip size filtering.
- `max_price` (float | None): Maximum price in USD (inclusive). Listings with a price strictly above this value are excluded. Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict in the list has these fields:
- `id` (str): Unique listing identifier (e.g., "lst_006")
- `title` (str): Human-readable listing name (e.g., "Graphic Tee — 2003 Tour Bootleg Style")
- `description` (str): Seller's free-text description of the item
- `category` (str): One of: tops, bottoms, outerwear, shoes, accessories
- `style_tags` (list[str]): Descriptive style keywords (e.g., ["vintage", "grunge", "graphic tee"])
- `size` (str): Size as listed (e.g., "M", "W30 L30", "XL (oversized)")
- `condition` (str): One of: excellent, good, fair
- `price` (float): Listed price in USD
- `colors` (list[str]): Colors in the item (e.g., ["black", "white"])
- `brand` (str | None): Brand name if known, else null
- `platform` (str): Where it's listed — one of: depop, thredUp, poshmark

Returns an empty list `[]` when no listings match — never raises an exception.

**What happens if it fails or returns nothing:**
If the list is empty, the agent sets `session["error"]` to a message explaining what search terms and filters were used and what the user could try differently — for example: "No listings found for 'vintage graphic tee' in size M under $30. Try removing the size filter, raising your budget, or using broader keywords like 'tee' or 'top'." The agent then returns the session immediately and does NOT call suggest_outfit or create_fit_card with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the LLM to suggest 1–2 complete outfit combinations that incorporate the thrifted item alongside pieces from the user's existing wardrobe. If the wardrobe is empty, it offers general styling advice instead of referencing specific owned pieces.

**Input parameters:**
- `new_item` (dict): A single listing dict (as returned by search_listings) representing the item the user is considering. Relevant fields: title, category, colors, style_tags, condition, price, platform.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: id (str), name (str), category (str), colors (list[str]), style_tags (list[str]), notes (str | None). The list may be empty.
- `style_profile` (dict | None): Optional persisted user preferences loaded from `data/style_profile.json`. When present (interaction_count > 0), adds a context block to the prompt describing the user's established style/color preferences from previous sessions.
- `trend_report` (dict | None): Optional output of `get_trend_report()`. When present, the `trend_summary` string is appended to the prompt so the LLM can factor in what's currently trending.

**What it returns:**
A non-empty string containing the LLM's outfit suggestions. When the wardrobe has items, the response names specific pieces from the wardrobe by name (e.g., "Pair with your baggy straight-leg jeans and chunky white sneakers..."). When the wardrobe is empty, the response gives general styling advice (e.g., "This tee pairs well with wide-leg denim or trousers. Look for chunky footwear to balance the relaxed silhouette."). Never returns an empty string.

**What happens if it fails or returns nothing:**
If the LLM call raises an exception (API error, timeout) the tool catches it and returns the string: "Could not generate outfit suggestions right now. Try again in a moment." The agent stores this fallback string in `session["outfit_suggestion"]` and proceeds to create_fit_card, which will detect the fallback and respond accordingly.

---

### Tool 3: create_fit_card

**What it does:**
Uses the LLM at higher temperature to generate a 2–4 sentence casual outfit caption — the kind someone would post as an Instagram or TikTok OOTD caption — based on the outfit suggestion and the thrifted item's details. Output should feel authentic and social-media-ready, not like a product listing.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from suggest_outfit(). Must be non-empty for a real caption to be generated.
- `new_item` (dict): The listing dict for the thrifted item. Used to naturally weave in the item name, price, and platform into the caption.

**What it returns:**
A 2–4 sentence string written in casual first-person social media tone. It mentions the thrifted item's name, price, and platform exactly once each, and captures the outfit's vibe in specific terms (e.g., "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤"). The caption sounds different each time because the LLM is prompted with temperature=1.1.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool immediately returns the error string: "Cannot create a fit card — outfit suggestion is missing. Try running the full search again." If the LLM call raises an exception, it returns: "Fit card generation failed. Here's the outfit suggestion instead: [outfit]." The agent stores whatever string is returned in `session["fit_card"]` and surfaces it to the user.

---

### Additional Tools (if any)

---

### Tool 4: compare_price *(stretch)*

**What it does:**
Compares the item's price against comparable listings in the mock dataset to estimate whether the price is fair, above average, or a great deal — with specific dollar amounts and percentages in the reasoning.

**Input parameters:**
- `item` (dict): A listing dict to evaluate. Uses `category`, `style_tags`, `price`, and `id` fields.

**What it returns:**
A dict with four keys:
- `assessment` (str): One of `"great deal"` (≥20% below avg), `"fair price"` (within 10%), `"above average"` (>10% above), or `"unknown"` (no comparables found)
- `reasoning` (str): Human-readable sentence with exact dollar amounts and percentage diff (e.g., "At $24.00, this is 16% above the average $20.73 across 11 comparable tops listings.")
- `avg_comparable_price` (float | None): Average price of comparable items used in the comparison
- `comparable_count` (int): Number of listings used for comparison

Comparables are selected by: same `category` + at least one shared `style_tag`. Falls back to same category only if no style-matched comparables exist. No LLM call — pure Python statistics.

**What happens if it fails or returns nothing:**
If no comparables exist at all, returns `{assessment: "unknown", reasoning: "Not enough comparable listings...", avg_comparable_price: None, comparable_count: 0}`. Never raises an exception.

---

### Tool 5: get_trend_report *(stretch)*

**What it does:**
Checks the item's style tags against a mock seasonal trend dataset (`data/trends.json`) that simulates a fashion platform API response. Returns which of the item's tags are currently trending and a human-readable summary that is injected into the `suggest_outfit` prompt.

**Input parameters:**
- `style_tags` (list[str]): The style tag list from the listing dict being evaluated.

**What it returns:**
A dict with four keys:
- `trending_styles` (list[str]): All currently trending style names in the dataset
- `item_trending_tags` (list[str]): Which of the item's style tags appear in the trend data
- `trend_summary` (str): Human-readable string describing trend status (injected into suggest_outfit prompt)
- `momentum` (dict): `{style_tag: momentum_string}` for matched tags, where momentum is `"rising"`, `"peak"`, or `"declining"`

**What happens if it fails or returns nothing:**
If none of the item's tags match the trend data, returns a summary pointing to what IS trending instead. No LLM call. If `data/trends.json` is missing, raises `FileNotFoundError` — agent catches this and leaves `session["trend_report"]` as None (suggest_outfit runs without trend context).

---

### Tool 6 & 7: load_style_profile / save_style_profile *(stretch)*

**What they do:**
Persist user style preferences across sessions. `save_style_profile(item)` appends the selected item's style_tags, colors, and category to `data/style_profile.json` after each completed interaction. `load_style_profile()` reads this file at the start of each run and returns the accumulated preferences.

**Input parameters:**
- `save_style_profile`: `item` (dict) — the selected listing dict from the completed interaction
- `load_style_profile`: no parameters

**What they return:**
- `save_style_profile`: None (writes to disk)
- `load_style_profile`: dict with keys `preferred_styles` (list[str]), `preferred_colors` (list[str]), `preferred_categories` (list[str]), `interaction_count` (int). Returns zeroed-out dict if no file exists yet.

**What happens if it fails or returns nothing:**
`load_style_profile` returns an empty profile (interaction_count=0) if the file doesn't exist — the agent proceeds normally, just without personalization. `save_style_profile` failure (disk error) is not caught; it propagates but does not affect the UI output since it runs at the very end of a successful interaction.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop runs as a linear sequence of conditional checks inside `run_agent()`. Each step only proceeds if the previous step succeeded; otherwise it sets an error and returns early. Here is the exact conditional logic:

1. **Initialize session + load style profile** — call `_new_session(query, wardrobe)` and `load_style_profile()`. Style profile is loaded here so it's available throughout the run without re-reading the file.

2. **Parse the query** — use the LLM to extract `{description, size, max_price}` as JSON. Falls back to regex if the LLM call fails. Store in `session["parsed"]`. If parsing fails entirely, set `session["error"]` and return early.

3. **Search with automatic retry** — call `search_listings(description, size, max_price)`.
   - **If results empty AND size was specified**: retry with `size=None`. If results found, set `session["retry_note"]` = `"No results for size X — showing results for any size instead."` Continue.
   - **If still empty AND max_price was specified**: retry with `max_price=None` too. Update `session["retry_note"]`. Continue.
   - **If still empty after both retries**: set `session["error"]` = `"No listings found for '...' even after loosening filters."` Return immediately — do NOT call any further tools.
   - **If results non-empty**: set `session["selected_item"] = search_results[0]`. Continue.

4. **Price comparison** — call `compare_price(session["selected_item"])`. Store in `session["price_comparison"]`. Always returns a dict — no early exit.

5. **Trend report** — call `get_trend_report(session["selected_item"]["style_tags"])`. Store in `session["trend_report"]`. Result is passed into suggest_outfit so trend context influences the LLM.

6. **Suggest outfit** — call `suggest_outfit(selected_item, wardrobe, style_profile=style_profile, trend_report=session["trend_report"])`. Store in `session["outfit_suggestion"]`. Always produces a non-empty string.

7. **Create fit card** — call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store in `session["fit_card"]`.

8. **Save style profile** — call `save_style_profile(session["selected_item"])` to persist preferences for next session. Runs last so a failure here doesn't affect the UI output.

9. **Return session** — `session["error"]` is None. Caller reads `fit_card`, `outfit_suggestion`, `price_comparison`, `trend_report`, and `retry_note`.

The agent does NOT call suggest_outfit, create_fit_card, compare_price, or get_trend_report unconditionally — it only reaches them if at least one search result was found (after retries). The retry logic means the agent behaves differently for a zero-result query with filters (retries) versus one that is truly unfindable (final error).

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single Python dict called `session`, initialized by `_new_session()` at the start of each call to `run_agent()`. The dict is the single source of truth for the entire interaction. Here is what is stored and when:

| Key | Type | Set when | Used by |
|-----|------|----------|---------|
| `query` | str | Initialization | Displayed in error messages |
| `parsed` | dict `{description, size, max_price}` | After query parsing | Passed as args to search_listings |
| `search_results` | list[dict] | After search_listings (+ retries) | Checked for emptiness; first item selected |
| `selected_item` | dict (listing) | After non-empty search_results | Passed to compare_price, get_trend_report, suggest_outfit, create_fit_card, save_style_profile |
| `wardrobe` | dict | Initialization (from caller) | Passed to suggest_outfit |
| `outfit_suggestion` | str | After suggest_outfit returns | Passed to create_fit_card |
| `fit_card` | str | After create_fit_card returns | Returned to UI |
| `error` | str or None | On any early-exit failure | Checked by caller before reading other fields |
| `retry_note` | str or None | After a successful retry with looser filters | Shown as warning banner in UI listing panel |
| `price_comparison` | dict or None | After compare_price returns | Displayed in Price & Trends panel |
| `trend_report` | dict or None | After get_trend_report returns | Passed to suggest_outfit; displayed in Price & Trends panel |

Style profile is loaded at the start of `run_agent()` as a local variable (not a session key) and passed directly into `suggest_outfit`. It is persisted by `save_style_profile()` at the end of a successful run, writing to `data/style_profile.json` on disk — the only data that lives outside the session dict.

The user never re-enters anything between steps. Every tool receives its inputs directly from the session dict, not from the user.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results with all filters applied | Agent retries: first without size, then without price ceiling. Sets `session["retry_note"]` if retry succeeds. Only sets `session["error"]` and exits early if all retries return empty. |
| search_listings | No results even after retries | `session["error"]` = "No listings found for '...' even after loosening filters. Try different keywords." Returns early — does not call any further tools. |
| suggest_outfit | Wardrobe is empty (items list is []) | Tool detects empty wardrobe before calling LLM. Switches to a general-styling prompt. Returns a non-empty general-advice string — no exception raised. |
| suggest_outfit | LLM API call raises an exception | Tool catches the exception and returns "Could not generate outfit suggestions right now. Try again in a moment." Agent stores this string and continues to create_fit_card. |
| create_fit_card | outfit argument is empty or whitespace | Guard clause at top of function returns "Cannot create a fit card — outfit suggestion is missing. Try running the full search again." Does not call the LLM. |
| create_fit_card | LLM API call raises an exception | Returns "Fit card generation failed. Here's the outfit suggestion instead: [outfit]." Surfaced to the user as final output. |
| compare_price | No comparable listings in dataset | Returns `{assessment: "unknown", reasoning: "Not enough comparable listings..."}`. Agent stores this and continues — no early exit. |
| get_trend_report | None of item's tags match trend data | Returns summary pointing to what IS trending instead. Agent stores and continues. |

---

## Architecture

```
User query (natural language)
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          run_agent()                                 │
│                       (Planning Loop)                                │
│                                                                      │
│  Step 1: _new_session() + load_style_profile()                      │
│          → session dict initialized; style_profile loaded from disk  │
│                │                                                     │
│  Step 2: Parse query (LLM → JSON, regex fallback)                    │
│          → session["parsed"] = {description, size, max_price}        │
│                │                                                     │
│                ▼                                                     │
│  Step 3: search_listings(description, size, max_price)               │
│          → session["search_results"]                                 │
│                │                                                     │
│         ┌──────┴─────────────────┐                                   │
│         │ results == []           │ results non-empty                │
│         ▼                        └──────────────────────────────┐    │
│   retry without size?                                           │    │
│         │ yes → search again                                    │    │
│         │   found? → session["retry_note"] set                  │    │
│         │   still empty → retry without price too               │    │
│         │     found? → session["retry_note"] updated            │    │
│         │     still empty → session["error"] set                │    │
│         │                   return ◄── early exit               │    │
│         │                                                        │    │
│         └─────────────────────────────────────────────────────► │    │
│                                                                  │    │
│                        session["selected_item"] = results[0]    │    │
│                                                                  ▼    │
│  Step 4: compare_price(selected_item)                                │
│          → session["price_comparison"] = {assessment, reasoning,...} │
│                │                                                     │
│  Step 5: get_trend_report(selected_item["style_tags"])               │
│          → session["trend_report"] = {trending_styles, summary,...}  │
│                │                                                     │
│                ▼                                                     │
│  Step 6: suggest_outfit(selected_item, wardrobe,                     │
│                          style_profile, trend_report)                │
│                │                                                     │
│         ┌──────┴──────────────┐                                      │
│         │ wardrobe empty       │ wardrobe has items                  │
│         ▼                     ▼                                      │
│    General styling       Specific outfit using                       │
│    advice (LLM)          named wardrobe pieces +                     │
│                          style profile context +                     │
│                          trend context (all in prompt)               │
│         └──────┬──────────────┘                                      │
│                │                                                     │
│        session["outfit_suggestion"] = str                            │
│                │                                                     │
│  Step 7: create_fit_card(outfit_suggestion, selected_item)           │
│                │                                                     │
│         ┌──────┴──────────────┐                                      │
│         │ outfit empty        │ normal                               │
│         ▼                     ▼                                      │
│    Error string          Caption (LLM, temp=1.1)                    │
│         └──────┬──────────────┘                                      │
│                │                                                     │
│        session["fit_card"] = str                                     │
│                │                                                     │
│  Step 8: save_style_profile(selected_item)                           │
│          → writes data/style_profile.json (persists for next session)│
│                │                                                     │
│  Step 9: return session (error = None)                               │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
Caller reads session["error"] first.
If set  → display error message; all output fields are None.
If None → display all four panels:
  • listing panel:      selected_item details + retry_note (if set)
  • outfit panel:       outfit_suggestion
  • fit card panel:     fit_card
  • price/trend panel:  price_comparison + trend_report

State flows:
  query/wardrobe ─────────────────────────────► session init
  style_profile.json ─────────────────────────► load_style_profile() → local var
  parsed params ──────────────────────────────► search_listings()
  search_results[0] ──────────────────────────► session["selected_item"]
  selected_item ──────────────────────────────► compare_price() → session["price_comparison"]
  selected_item["style_tags"] ────────────────► get_trend_report() → session["trend_report"]
  selected_item + wardrobe + profile + trends ► suggest_outfit() → session["outfit_suggestion"]
  outfit_suggestion + selected_item ──────────► create_fit_card() → session["fit_card"]
  selected_item ──────────────────────────────► save_style_profile() → style_profile.json
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 — search_listings:**
I will give Claude the Tool 1 section of this planning.md (inputs with types, return value with all fields listed, failure mode) plus the docstring from tools.py showing the TODO steps. I'll ask it to implement the function using `load_listings()` from `utils/data_loader.py`, scoring by keyword overlap across `title`, `description`, and `style_tags`. Before using the generated code I will verify: (a) it filters by both size and price before scoring, (b) it drops zero-score listings, (c) it returns an empty list (not raises) when nothing matches. I will test it with three queries: one that returns multiple results, one filtered by size and price, and one that returns nothing.

**Tool 2 — suggest_outfit:**
I will give Claude the Tool 2 section of this planning.md plus the wardrobe_schema.json contents so it understands the wardrobe dict structure. I'll ask it to implement the function with a branch for empty vs non-empty wardrobe, using the Groq client already initialized in tools.py (llama-3.3-70b-versatile). Before using it I will verify: (a) the empty-wardrobe branch calls the LLM with a general-styling prompt, (b) the non-empty branch formats wardrobe items into the prompt by name, (c) the function catches API exceptions and returns a fallback string. I will test with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

**Tool 3 — create_fit_card:**
I will give Claude the Tool 3 section of this planning.md, the caption style requirements (casual, first-person, mentions item name/price/platform once each, temperature=1.1). I'll ask it to implement the guard clause first, then the LLM call. Before using it I will verify: (a) an empty `outfit` string returns the error message without calling the LLM, (b) a real outfit string produces a caption that reads like a social post (not a product description), (c) calling it twice with the same input produces noticeably different outputs. I will run it three times and read the captions aloud to check tone.

**Milestone 4 — Planning loop and state management:**

I will give Claude the Architecture diagram from this planning.md plus the `_new_session()` dict keys from agent.py and the Planning Loop section describing each conditional branch. I'll ask it to implement `run_agent()` so that: (a) it parses the query using an LLM call that returns a JSON object with `description`, `size`, and `max_price` fields, (b) it checks `search_results` for emptiness before proceeding, (c) it stores each tool's output in the correct session key before calling the next tool. Before using the generated code I will verify: (a) running the CLI test at the bottom of agent.py with the no-results query hits the early-exit branch, (b) running it with the graphic-tee query populates all four output fields, (c) `session["selected_item"]` is the same dict object passed into suggest_outfit (not a copy with different fields).

**Stretch features — compare_price, get_trend_report, style profile, retry logic:**

For `compare_price` and `get_trend_report` I gave Claude each tool's spec block (inputs, return dict fields, failure mode) from this planning.md and asked it to implement them in tools.py without any LLM calls — pure Python statistics and file reads. I verified: (a) compare_price returns "great deal" for items significantly below average and "above average" for ones above, (b) get_trend_report correctly matches style tags and builds a human-readable summary, (c) neither function raises on edge cases (no comparables, no matching tags).

For retry logic I gave Claude the Planning Loop section above (step 3) and asked it to add the two retry branches inside `run_agent()` after the initial search. I verified by running `run_agent("vintage graphic tee size XXS under $50", ...)` and confirming `session["retry_note"]` was set and `session["selected_item"]` was not None.

For style profile I gave Claude the Tool 6 & 7 spec above and asked it to implement `load_style_profile()` and `save_style_profile()` using `json.load/dump`. I verified by running two sequential interactions and checking that `interaction_count` incremented and styles accumulated without duplicates.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse the query:**
The agent calls the LLM with a parsing prompt to extract structured parameters from the query. The LLM returns `{description: "vintage graphic tee", size: null, max_price: 30.0}`. (No size was specified in the query, so size is null.) These values are stored in `session["parsed"]`.

**Step 2 — Search listings:**
The agent calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The function loads all listings, drops any with price > 30.0 (removing lst_004 at $45, etc.), then scores the remaining ones by keyword overlap. Listings with "graphic tee" or "vintage" in their title, description, or style_tags score highest. The top result is **lst_006: "Graphic Tee — 2003 Tour Bootleg Style"** at $24 on depop. `session["search_results"]` = [lst_006, lst_002, ...] and `session["selected_item"]` = lst_006.

**Step 3 — Suggest outfit:**
The agent calls `suggest_outfit(selected_item=lst_006, wardrobe=get_example_wardrobe())`. The wardrobe has 10 items, so the non-empty branch runs. The LLM prompt includes the tee's details (black, graphic, grunge/streetwear style_tags) and the wardrobe items by name. The LLM returns something like: "Pair this faded bootleg tee with your baggy straight-leg dark-wash jeans and chunky white sneakers for an effortless streetwear look. Roll the sleeves once. Layer your vintage black denim jacket over the top if it's chilly — the cropped fit balances the boxy tee perfectly." This is stored in `session["outfit_suggestion"]`.

**Step 4 — Create fit card:**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=lst_006)`. The LLM generates a caption at temperature=1.1: "thrifted this faded bootleg tee off depop for $24 and it instantly became my go-to 🖤 baggy jeans, chunky sneakers, and my old denim jacket on top — effortless every time. if you know you know." This is stored in `session["fit_card"]`.

**Final output to user:**
```
Found: Graphic Tee — 2003 Tour Bootleg Style ($24, depop, good condition)

Outfit suggestion:
Pair this faded bootleg tee with your baggy straight-leg dark-wash jeans and
chunky white sneakers for an effortless streetwear look. Roll the sleeves once.
Layer your vintage black denim jacket over the top if it's chilly.

Fit card:
thrifted this faded bootleg tee off depop for $24 and it instantly became my
go-to 🖤 baggy jeans, chunky sneakers, and my old denim jacket on top —
effortless every time. if you know you know.
```

**Error path (no results):**
If the query were "designer ballgown size XXS under $5", search_listings would return []. The agent would set `session["error"] = "No listings found for 'designer ballgown' in size XXS under $5. Try removing the size filter, raising your budget, or using a broader search term like 'formal dress'."` and return immediately. suggest_outfit and create_fit_card are never called.
