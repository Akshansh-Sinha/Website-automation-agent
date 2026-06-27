# Website Automation Agent

## Problem Statement
How might we build an intelligent browser agent that autonomously navigates a real webpage,
identifies form elements visually, and fills and submits a form — demonstrating AI-driven
browser control with clean, grader-readable architecture?

## Recommended Direction

A **ReAct Vision Agent** using Python + Playwright + Gemini (gemini-2.5-flash).

The agent operates in a loop: at each step, it takes a screenshot of the current viewport,
encode it as base64, send it to Gemini with the task description and conversation history.
Gemini returns a brief reasoning statement followed by a single tool call. The tool executes,
a new screenshot is taken, and the loop continues until Gemini signals completion.

All 7 required tools (`take_screenshot`, `open_browser`, `navigate_to_url`, `click_on_screen`,
`send_keys`, `scroll`, `double_click`) are implemented as clean Python functions wrapping
Playwright's async API. The agent is task-specific but architecturally clean — swapping the
task prompt is all that's needed to target a different form.

The reasoning trace (Gemini's "I can see... I will now...") is printed to stdout in real time,
making the agent's decision-making transparent and readable. A final screenshot capturing the
success toast is saved as `screenshots/final.png`.

## Key Assumptions to Validate

- [ ] Gemini can accurately estimate click coordinates from a 1280×800 screenshot
      → Test by running the agent once and checking if clicks land on the right elements
- [ ] The shadcn demo form is visible after a single scroll down the page
      → Validate by checking viewport height vs. form position on the page
- [ ] The form's validation constraints (min 5 chars title, min 20 chars description)
      are met by Gemini's chosen fill values
      → Verify by reading the Zod schema in the page source

## MVP Scope

**In:**
- `browser_tools.py` — 7 tools, Playwright async, headed Chromium
- `llm_client.py` — Gemini client, tool-use schema, screenshot → base64 encoding
- `test_browser.py` — Smoke tests for the tool implementation
- `agent.py` — ReAct loop, task prompt, 15-step guard, reasoning trace printed to stdout
- `requirements.txt` — `playwright`, `google-genai`, `python-dotenv`
- `.env.example` — `GEMINI_API_KEY=`
- `screenshots/` — auto-created directory, stores per-step PNGs
- `README.md` — setup, run, troubleshooting

**Out:**
- No web UI or dashboard
- No generalisation to arbitrary URLs
- No retry logic on failed tool calls (agent self-corrects via new screenshot)
- No test suite

## Not Doing (and Why)

- **Multi-agent Planner/Executor** — overkill for a single-form task; adds coordination
  complexity with zero payoff at this scope
- **DOM-assisted hybrid mode** — defeats the point of demonstrating visual intelligence;
  the assignment rewards AI reasoning, not selector engineering
- **Annotated bounding boxes (Pillow CV)** — requires real CV or accessibility tree;
  basic edge detection on a CSS-rendered page would be unreliable
- **Generalisation to any URL** — out of scope; clean architecture means it is a
  one-line change anyway
- **Headless mode** — demonstration value of watching the agent work in real time
  outweighs the speed benefit

## Open Questions

- ~~Does the grader run this locally?~~ **Resolved: yes — README covers full local setup**
- ~~Should the agent stop after submit or keep going?~~ **Resolved: keep going, max 15 steps**
- ~~Is there a max-iteration budget concern?~~ **Resolved: 15-step guard in `agent.py`**
