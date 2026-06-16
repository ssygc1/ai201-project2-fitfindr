"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns a tuple of four strings:
        (listing_text, outfit_suggestion, fit_card, price_trend_text)
    """
    # Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", "", ""

    wardrobe = (
        get_example_wardrobe() if wardrobe_choice == "Example wardrobe" else get_empty_wardrobe()
    )

    session = run_agent(user_query.strip(), wardrobe)

    if session["error"]:
        return session["error"], "", "", ""

    item = session["selected_item"]

    # Panel 1: listing details + retry note if search was loosened
    retry_banner = f"⚠️ {session['retry_note']}\n\n" if session.get("retry_note") else ""
    listing_text = (
        f"{retry_banner}"
        f"{item['title']}\n"
        f"Price:     ${item['price']:.2f}\n"
        f"Platform:  {item['platform']}\n"
        f"Size:      {item['size']}\n"
        f"Condition: {item['condition']}\n"
        f"Colors:    {', '.join(item['colors'])}\n"
        f"Style:     {', '.join(item['style_tags'])}\n\n"
        f"{item['description']}"
    )

    # Panel 4: price comparison + trend report
    price_trend_lines = []
    pc = session.get("price_comparison")
    if pc and pc["assessment"] != "unknown":
        emoji = {"great deal": "🟢", "fair price": "🟡", "above average": "🔴"}.get(pc["assessment"], "⚪")
        price_trend_lines.append(f"Price: {emoji} {pc['assessment'].upper()}")
        price_trend_lines.append(pc["reasoning"])
        price_trend_lines.append("")

    tr = session.get("trend_report")
    if tr:
        price_trend_lines.append("Trend:")
        price_trend_lines.append(tr["trend_summary"])

    price_trend_text = "\n".join(price_trend_lines) if price_trend_lines else "No price/trend data."

    return listing_text, session["outfit_suggestion"], session["fit_card"], price_trend_text


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )
            pricetend_output = gr.Textbox(
                label="💰 Price & Trends",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output, pricetend_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output, pricetend_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
