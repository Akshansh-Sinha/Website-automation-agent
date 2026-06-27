# Website Automation Agent

A ReAct vision agent that autonomously navigates a real browser, identifies
web form elements by **visual reasoning** (no hardcoded selectors), and fills
and submits a form — demonstrating AI-driven browser control as a mini
[Browser Use](https://github.com/browser-use/browser-use).

---

## What it does

1. Opens a headed Chromium browser window (you can watch it work).
2. Navigates to [shadcn/ui — React Hook Form docs](https://ui.shadcn.com/docs/forms/react-hook-form).
3. Scrolls down to find the **Bug Report** demo form.
4. Fills in the **Bug Title** field with a valid title (5–32 chars).
5. Fills in the **Description** textarea with a valid description (20–100 chars).
6. Clicks **Submit**.
7. Captures a final screenshot confirming the success toast.
8. Saves a screenshot after every step to `screenshots/`.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      agent.py                            │
│                                                          │
│   ┌─────────────┐   screenshot (base64)  ┌───────────┐  │
│   │ BrowserTools│ ──────────────────────►│ LLMClient │  │
│   │ (Playwright)│                        │ (Gemini)  │  │
│   │             │ ◄── tool call ─────────│           │  │
│   └─────────────┘                        └───────────┘  │
│                                                          │
│   ReAct loop:  Perceive → Reason → Act → Observe        │
│   Max steps:   15                                        │
└──────────────────────────────────────────────────────────┘
```

### Files

| File | Purpose |
|---|---|
| `agent.py` | Main entry point. Owns the ReAct loop, step counter, and tool dispatcher. |
| `browser_tools.py` | All 7 browser tool implementations (Playwright async API). |
| `llm_client.py` | Gemini API client. Tool schemas, system prompt, conversation history. |
| `requirements.txt` | Python dependencies. |
| `.env.example` | API key template. |
| `screenshots/` | Auto-created. One PNG per agent step. |

### Tool inventory

| Tool | Description |
|---|---|
| `open_browser` | Launch headed Chromium, 1280×800 viewport |
| `navigate_to_url` | Go to a URL, wait for network idle |
| `take_screenshot` | Capture viewport → base64 PNG (sent to Gemini) |
| `click_on_screen(x, y)` | Single mouse click at pixel coordinates |
| `send_keys(text)` | Type into the focused element |
| `scroll(dx, dy)` | Mouse-wheel scroll; positive dy = down |
| `double_click(x, y)` | Double-click (select text before replacing) |

---

## Prerequisites

- Python 3.11 or higher
- A [Gemini API key](https://aistudio.google.com/) with access to
  `gemini-2.5-flash`

---

## Setup

```bash
# 1. Clone / enter the project directory
cd Website-automation-agent

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright's Chromium browser binary
playwright install chromium

# 5. Configure your API key
cp .env.example .env
# Open .env and replace  your_gemini_api_key_here  with your real key
```

---

## Run

```bash
python agent.py
```

A Chromium window will open. You will see the agent:

1. Load the shadcn/ui docs page.
2. Print its reasoning for each step in the terminal.
3. Scroll, click, and type autonomously.
4. Submit the form and confirm the success toast.

**Example terminal output:**

```
############################################################
  Website Automation Agent
  Target: https://ui.shadcn.com/docs/forms/react-hook-form
  Max steps: 15
############################################################

[Agent] Navigating to https://ui.shadcn.com/docs/forms/react-hook-form …
[Agent] Taking initial screenshot …

============================================================
  STEP 1 / 15
============================================================

Reasoning:
  I can see the shadcn/ui React Hook Form documentation page. The page
  shows the heading and some content but the demo form is not yet visible.
  I need to scroll down to find the Bug Report form.

Action:  scroll(delta_x=0, delta_y=400)
Result:  {'status': 'scrolled', 'delta_x': 0, 'delta_y': 400}

...

[Agent] Task complete: Successfully filled Bug Title with "Login button
not working on mobile" and Description with a detailed report, then
clicked Submit. The success toast appeared confirming submission.

[Agent] Done. Screenshots saved to screenshots/
```

---

## Screenshots

Every step is saved to `screenshots/` as `step_NNN_label.png`.
The final screenshot shows the submitted form and the confirmation toast.

---

## How the intelligence works

The agent uses **pure visual reasoning** — it receives no DOM access,
no CSS selectors, and no hardcoded element positions.

At each step:
1. `take_screenshot()` captures the viewport as a PNG and encodes it as base64.
2. The image is sent to **Gemini gemini-2.5-flash** alongside the conversation
   history (which contains all prior actions and their results).
3. Gemini describes what it sees (e.g. *"I can see a text input labelled Bug
   Title"*) and calls exactly one tool.
4. The tool executes in the browser and the result is appended to conversation
   history.
5. A fresh screenshot is taken and the loop continues.

This mirrors how [Browser Use](https://github.com/browser-use/browser-use)
works: the LLM is the "brain" and the browser tools are the "hands".

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Your Gemini API key from aistudio.google.com |

The max step limit (default 15) can be changed by editing `MAX_STEPS` in
`agent.py`.

---

## Troubleshooting

**`GEMINI_API_KEY is not set`**
→ Make sure you copied `.env.example` to `.env` and added your real key.

**`playwright install chromium` fails**
→ Try `python -m playwright install chromium` or check Playwright's
  [installation docs](https://playwright.dev/python/docs/intro).

**The browser opens but the agent can't find the form**
→ The page may load differently on your network. Check `screenshots/` to
  see what the agent saw. Increasing `MAX_STEPS` in `agent.py` may help.

**`ModuleNotFoundError: No module named 'google'`**
→ Make sure your virtual environment is active and you ran
  `pip install -r requirements.txt`.
