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

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop runs as a linear sequence of conditional checks inside `run_agent()`. Each step only proceeds if the previous step succeeded; otherwise it sets an error and returns early. Here is the exact conditional logic:

1. **Initialize session** — call `_new_session(query, wardrobe)` to create the session dict with all fields set to their defaults.

2. **Parse the query** — use the LLM (or regex) to extract three values from the natural-language query: `description` (str), `size` (str or None), `max_price` (float or None). Store in `session["parsed"]`. If parsing fails entirely, set `session["error"] = "Could not understand your query. Please describe what you're looking for, your size, and a maximum price."` and return early.

3. **Search** — call `search_listings(description, size, max_price)` with the parsed values. Store the result in `session["search_results"]`.
   - **If `session["search_results"]` is empty**: set `session["error"]` to a specific message naming the filters used and suggesting what to try differently (e.g., remove size, raise price). Return the session immediately. Do NOT continue.
   - **If results are non-empty**: set `session["selected_item"] = session["search_results"][0]` (top result). Continue to step 4.

4. **Suggest outfit** — call `suggest_outfit(session["selected_item"], session["wardrobe"])`. Store the string result in `session["outfit_suggestion"]`. This step always produces a non-empty string (the tool handles its own failures internally), so no early-return check is needed here.

5. **Create fit card** — call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store the result in `session["fit_card"]`. Again, the tool handles its own failures and always returns a string.

6. **Return session** — `session["error"]` is None at this point, so the caller knows all three tools ran successfully.

The agent does NOT call suggest_outfit or create_fit_card unconditionally — it only reaches them if search_listings returned at least one result. This means the agent's behavior is visibly different for a query that finds nothing (stops at step 3, returns an error) versus one that succeeds (runs all three tools).

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single Python dict called `session`, initialized by `_new_session()` at the start of each call to `run_agent()`. The dict is the single source of truth for the entire interaction. Here is what is stored and when:

| Key | Type | Set when | Used by |
|-----|------|----------|---------|
| `query` | str | Initialization | Displayed in error messages |
| `parsed` | dict `{description, size, max_price}` | After query parsing | Passed as args to search_listings |
| `search_results` | list[dict] | After search_listings returns | Checked for emptiness; first item selected |
| `selected_item` | dict (listing) | After non-empty search_results | Passed to suggest_outfit and create_fit_card |
| `wardrobe` | dict | Initialization (from caller) | Passed to suggest_outfit |
| `outfit_suggestion` | str | After suggest_outfit returns | Passed to create_fit_card |
| `fit_card` | str | After create_fit_card returns | Returned to the UI / caller |
| `error` | str or None | On any early-exit failure | Checked by caller before reading other fields |

The user never re-enters anything between steps. The item returned by search_listings is stored in `session["selected_item"]` and passed directly into suggest_outfit. The outfit string from suggest_outfit is stored in `session["outfit_suggestion"]` and passed directly into create_fit_card. No information is passed via global variables or external files — everything travels through this single session dict within one function call.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the query (empty list returned) | Agent sets `session["error"]` = "No listings found for '[description]' in size [size] under $[max_price]. Try removing the size filter, raising your budget, or using broader keywords like '[shorter keyword]'." Returns session early — does not call suggest_outfit or create_fit_card. |
| suggest_outfit | Wardrobe is empty (items list is []) | Tool detects empty wardrobe before calling LLM. Switches to a general-styling prompt asking the LLM for generic pairing advice (colors, silhouettes, shoe types that work with the item). Returns a non-empty general-advice string — no exception raised. |
| create_fit_card | outfit argument is empty or whitespace | Tool guards at the top of the function. Returns the error string: "Cannot create a fit card — outfit suggestion is missing. Try running the full search again." Does not call the LLM. |
| suggest_outfit | LLM API call raises an exception | Tool catches the exception and returns "Could not generate outfit suggestions right now. Try again in a moment." Agent stores this string and continues to create_fit_card. |
| create_fit_card | LLM API call raises an exception | Tool catches the exception and returns "Fit card generation failed. Here's the outfit suggestion instead: [outfit]." Surfaced to the user as the final output. |

---

## Architecture

```
User query (natural language)
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│                       run_agent()                                 │
│                    (Planning Loop)                                │
│                                                                   │
│  Step 1: _new_session(query, wardrobe)                           │
│          → session dict initialized                               │
│                │                                                  │
│  Step 2: Parse query (LLM or regex)                               │
│          → session["parsed"] = {description, size, max_price}     │
│                │                                                  │
│                ▼                                                  │
│  Step 3: search_listings(description, size, max_price)            │
│          → session["search_results"] = [listing, ...]             │
│                │                                                  │
│         ┌──────┴──────────────────────────────┐                   │
│         │ results == []                        │ results non-empty │
│         ▼                                     ▼                   │
│  [ERROR] session["error"] =            session["selected_item"]   │
│  "No listings found..."                = search_results[0]        │
│  return session ◄── early exit               │                   │
│                                              ▼                    │
│                              Step 4: suggest_outfit(              │
│                                        selected_item,             │
│                                        session["wardrobe"])       │
│                                        │                          │
│                              ┌─────────┴──────────────┐           │
│                              │ wardrobe.items == []    │ has items │
│                              ▼                         ▼           │
│                         General styling          Specific outfits  │
│                         advice (LLM)             using wardrobe   │
│                              └─────────┬──────────────┘           │
│                                        │                          │
│                              session["outfit_suggestion"] = str   │
│                                        │                          │
│                                        ▼                          │
│                              Step 5: create_fit_card(             │
│                                        outfit_suggestion,         │
│                                        selected_item)             │
│                                        │                          │
│                              ┌─────────┴──────────────┐           │
│                              │ outfit empty/error      │ normal    │
│                              ▼                         ▼           │
│                         Error string            Caption (LLM,     │
│                         returned                temp=1.1)         │
│                              └─────────┬──────────────┘           │
│                                        │                          │
│                              session["fit_card"] = str            │
│                              session["error"] = None              │
│                                        │                          │
│                              return session                        │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
Caller reads session["error"] first.
If None → display session["fit_card"] and session["outfit_suggestion"].
If set  → display error message and stop.

State flows (arrows show what data moves where):
  query ──────────────────────────────────────────► session["query"]
  wardrobe ───────────────────────────────────────► session["wardrobe"]
  parsed {description, size, max_price} ──────────► search_listings()
  search_listings() result ───────────────────────► session["search_results"]
  search_results[0] ──────────────────────────────► session["selected_item"]
  selected_item + wardrobe ───────────────────────► suggest_outfit()
  suggest_outfit() result ────────────────────────► session["outfit_suggestion"]
  outfit_suggestion + selected_item ──────────────► create_fit_card()
  create_fit_card() result ───────────────────────► session["fit_card"]
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
