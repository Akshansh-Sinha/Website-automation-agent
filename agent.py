"""
agent.py
--------
Entry point for the Website Automation Agent.

Architecture: ReAct Vision Loop
  Perceive  → take_screenshot() sends the current viewport to Gemini
  Reason    → Gemini narrates what it sees and decides what to do next
  Act       → the chosen tool is dispatched to BrowserTools
  Observe   → the tool result is appended to conversation history
  Repeat    → until Gemini calls `done` or MAX_STEPS is reached

The agent keeps a full conversation history so Gemini has context of every
prior action and its outcome when choosing the next step.

Usage:
    python agent.py

Environment:
    GEMINI_API_KEY must be set in .env (see .env.example)
"""

import asyncio
import sys
from typing import Any

from browser_tools import BrowserTools
from llm_client import LLMClient


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_URL = "https://ui.shadcn.com/docs/forms/react-hook-form"
MAX_STEPS = 15          # Hard safety cap — the agent stops after this many steps
                        # even if it hasn't called `done` yet.


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

async def dispatch(tools: BrowserTools, tool_name: str, tool_input: dict[str, Any]) -> dict:
    """
    Map a tool name string to the corresponding BrowserTools method and call it.

    This is intentionally a flat dispatch table (not dynamic getattr) so that
    only the explicitly listed tools can be called — no arbitrary code execution.

    Args:
        tools:      The BrowserTools instance controlling the browser.
        tool_name:  Name of the tool as returned by the LLM.
        tool_input: Keyword arguments for the tool method.

    Returns:
        The dict result from the tool method.

    Raises:
        ValueError if tool_name is not a known tool.
    """
    match tool_name:
        case "open_browser":
            # The browser is already open; treat as a no-op if Gemini calls it.
            return {"status": "browser_already_open"}
        case "navigate_to_url":
            return await tools.navigate_to_url(**tool_input)
        case "take_screenshot":
            return await tools.take_screenshot(**tool_input)
        case "click_on_screen":
            return await tools.click_on_screen(**tool_input)
        case "send_keys":
            return await tools.send_keys(**tool_input)
        case "scroll":
            return await tools.scroll(**tool_input)
        case "double_click":
            return await tools.double_click(**tool_input)
        case _:
            raise ValueError(f"Unknown tool: {tool_name!r}")


# ---------------------------------------------------------------------------
# Pretty printing helpers
# ---------------------------------------------------------------------------

def _print_step_header(step: int, max_steps: int) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  STEP {step} / {max_steps}")
    print("=" * width)


def _print_reasoning(reasoning: str) -> None:
    if reasoning:
        print(f"\nReasoning:\n  {reasoning}")


def _print_action(tool_name: str, tool_input: dict) -> None:
    args = ", ".join(f"{k}={v!r}" for k, v in tool_input.items())
    print(f"\nAction:  {tool_name}({args})")


def _print_result(result: dict) -> None:
    # Omit the base64 blob from the console — it's very long and unhelpful.
    display = {k: v for k, v in result.items() if k != "base64"}
    print(f"Result:  {display}")


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

async def run_agent() -> None:
    """
    Orchestrate the full ReAct vision loop.

    Steps:
      1. Open the browser and navigate to the target URL.
      2. Take an initial screenshot to give Gemini its first view of the page.
      3. Loop: ask Gemini → execute tool → record result → repeat.
      4. Stop when Gemini calls `done` or MAX_STEPS is exhausted.
      5. Close the browser.
    """
    tools = BrowserTools()
    llm = LLMClient()

    print("\n" + "#" * 60)
    print("  Website Automation Agent")
    print(f"  Target: {TARGET_URL}")
    print(f"  Max steps: {MAX_STEPS}")
    print("#" * 60)

    try:
        # ── 1. Launch browser ──────────────────────────────────────────
        await tools.open_browser(headless=False)

        # ── 2. Navigate to target ──────────────────────────────────────
        print(f"\n[Agent] Navigating to {TARGET_URL} …")
        await tools.navigate_to_url(TARGET_URL)

        # ── 3. Initial screenshot ──────────────────────────────────────
        print("[Agent] Taking initial screenshot …")
        shot = await tools.take_screenshot(label="initial")

        # ── 4. ReAct loop ──────────────────────────────────────────────
        # We carry the previous tool_name and result forward so they can
        # be bundled with the next screenshot into ONE user message.
        prev_tool_name: str | None = None
        prev_result: dict | None = None

        for step in range(1, MAX_STEPS + 1):
            _print_step_header(step, MAX_STEPS)

            # --- Perceive + Reason + Act (ask Gemini) ---
            tool_name, tool_input, reasoning = llm.call(
                shot["base64"],
                prev_tool_name=prev_tool_name,
                prev_tool_result=prev_result,
            )

            _print_reasoning(reasoning)
            _print_action(tool_name, tool_input)

            # --- Terminal condition: Gemini signals completion ---
            if tool_name == "done":
                print(f"\n[Agent] Task complete: {tool_input.get('summary', '')}")
                break

            # --- Execute the tool ---
            try:
                result = await dispatch(tools, tool_name, tool_input)
            except Exception as exc:
                # If a tool fails, tell Gemini about it so it can recover.
                result = {"status": "error", "error": str(exc)}
                print(f"[Agent] Tool error: {exc}")

            _print_result(result)

            # --- Capture a fresh screenshot for the next iteration ---
            # This will be sent together with `result` as one user message.
            shot = await tools.take_screenshot()

            # --- Carry result forward to be included in next user message ---
            prev_tool_name = tool_name
            prev_result = result

        else:
            # Loop exhausted without `done` being called
            print(
                f"\n[Agent] Reached {MAX_STEPS}-step limit without completion. "
                "Check screenshots/ to see how far the agent got."
            )

    finally:
        # Always close the browser, even if an exception occurred.
        await tools.close_browser()
        print("\n[Agent] Done. Screenshots saved to screenshots/")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except EnvironmentError as exc:
        # Missing API key or other config problem — give a clear message.
        print(f"\n[Error] {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[Agent] Interrupted by user.")
        sys.exit(0)
