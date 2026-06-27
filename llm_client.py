"""
llm_client.py
-------------
Gemini API client for the ReAct vision agent.

Responsibilities:
  - Define the tool schemas Gemini can call (including the sentinel `done` tool)
  - Build the system prompt that governs the agent's behaviour
  - Maintain and update the conversation history (messages list)
  - Send screenshot + history to Gemini and parse out:
      (tool_name, tool_input, reasoning_text)
"""

import base64
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

load_dotenv()


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
# These are surfaced to Gemini as standard JSON schema function declarations.
# The `done` tool is a sentinel: when Gemini calls it the agent loop stops.

TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="open_browser",
                description=(
                    "Initialize and launch the browser instance. "
                    "The agent calls this automatically at startup before the task begins. "
                    "Do NOT call this tool — the browser is already open."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "headless": {
                            "type": "BOOLEAN",
                            "description": "Run without a visible window when true.",
                        }
                    },
                },
            ),
            types.FunctionDeclaration(
                name="navigate_to_url",
                description=(
                    "Direct the browser to a URL. "
                    "Wait for the page to fully load before returning."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "url": {
                            "type": "STRING",
                            "description": "The fully-qualified URL to navigate to.",
                        }
                    },
                    "required": ["url"],
                },
            ),
            types.FunctionDeclaration(
                name="take_screenshot",
                description=(
                    "Capture the current browser viewport as a PNG image. "
                    "Always call this before deciding what to click or type."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "label": {
                            "type": "STRING",
                            "description": "Optional short label for the screenshot filename.",
                        }
                    },
                },
            ),
            types.FunctionDeclaration(
                name="click_on_screen",
                description=(
                    "Perform a single left mouse click at the given viewport coordinates. "
                    "Use this to focus input fields, press buttons, or activate links. "
                    "Coordinates are in pixels; (0,0) is the top-left corner of the viewport."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "x": {"type": "INTEGER", "description": "Horizontal pixel coordinate."},
                        "y": {"type": "INTEGER", "description": "Vertical pixel coordinate."},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="send_keys",
                description=(
                    "Type text into the currently-focused element. "
                    "Always click the target field first with click_on_screen."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "text": {
                            "type": "STRING",
                            "description": "The text to type into the focused element.",
                        }
                    },
                    "required": ["text"],
                },
            ),
            types.FunctionDeclaration(
                name="scroll",
                description=(
                    "Scroll the page using the mouse wheel. "
                    "Positive delta_y scrolls DOWN; negative scrolls UP. "
                    "Use this to reveal content that is below the visible viewport."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "delta_x": {
                            "type": "INTEGER",
                            "description": "Horizontal scroll amount in pixels.",
                        },
                        "delta_y": {
                            "type": "INTEGER",
                            "description": "Vertical scroll amount in pixels (positive = down).",
                        },
                    },
                    "required": ["delta_x", "delta_y"],
                },
            ),
            types.FunctionDeclaration(
                name="double_click",
                description=(
                    "Perform a double mouse click at the given viewport coordinates. "
                    "Useful for selecting all existing text in an input field before replacing it."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "x": {"type": "INTEGER", "description": "Horizontal pixel coordinate."},
                        "y": {"type": "INTEGER", "description": "Vertical pixel coordinate."},
                    },
                    "required": ["x", "y"],
                },
            ),
            types.FunctionDeclaration(
                name="done",
                description=(
                    "Signal that the task is fully complete. "
                    "Call this only after you have confirmed the form was submitted successfully "
                    "(e.g. you can see a success toast or confirmation message)."
                ),
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "summary": {
                            "type": "STRING",
                            "description": "A brief description of what was accomplished.",
                        }
                    },
                    "required": ["summary"],
                },
            ),
        ]
    )
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a browser automation agent controlling a real Chromium browser.
Your viewport is 1280x800 pixels. Coordinates (0,0) are at the top-left corner.

YOUR TASK:
  1. The browser will already be on https://ui.shadcn.com/docs/forms/react-hook-form
  2. Scroll down to find the "Bug Report" demo form (it contains a "Bug Title" input and
     a "Description" textarea, plus Reset and Submit buttons).
  3. Click the "Bug Title" input and type a valid title (between 5 and 32 characters).
  4. Click the "Description" textarea and type a valid description (between 20 and 100 characters).
  5. Click the "Submit" button.
  6. Take a screenshot to confirm the success toast appeared.
  7. Call done() with a summary of what you accomplished.

RULES:
  - Always call take_screenshot first to see the current state before acting.
  - Reason briefly about what you see, then call exactly ONE tool per turn.
  - Scroll in increments of 300-400 pixels to find the form if it is not visible.
  - After clicking an input field, use send_keys to type into it.
  - After submitting, take a screenshot to confirm success before calling done().
  - Do NOT call done() until you have verified the form was submitted.
  - If a click does not seem to have worked, take a screenshot and try again.
"""


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Manages the conversation with Gemini and parses tool-use responses.

    Maintains a messages list that grows with each agent step so Gemini
    always has full context of what has been done so far.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your API key."
            )
        self._client = genai.Client(api_key=api_key)
        self._messages: list[types.Content] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def call(
        self,
        screenshot_b64: str,
        prev_tool_name: str | None = None,
        prev_tool_result: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], str]:
        """
        Send the latest screenshot to Gemini and get the next action.

        Args:
            screenshot_b64:    Base64-encoded PNG of the current viewport.
            prev_tool_name:    Name of the tool that was executed previously.
                               Pass None on the very first call.
            prev_tool_result:  dict returned by the BrowserTools method that
                               was just executed. Pass None on the first call.

        Returns:
            (tool_name, tool_input, reasoning)
              tool_name    - Name of the tool Gemini wants to call next.
              tool_input   - Keyword arguments for that tool.
              reasoning    - Gemini's plain-text narration (may be empty).
        """
        user_message = self._build_user_message(
            screenshot_b64,
            prev_tool_name=prev_tool_name,
            prev_tool_result=prev_tool_result,
        )
        self._messages.append(user_message)

        # Retry with exponential backoff on transient server errors (503/429)
        max_retries = 5
        retry_delay = 5  # seconds (default, overridden by retryDelay in 429 body)
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=self._messages,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=TOOLS,
                        temperature=0.0,
                    ),
                )
                break  # success — exit retry loop
            except genai_errors.ServerError as exc:
                if attempt == max_retries:
                    raise
                wait = retry_delay * attempt
                print(
                    f"[LLMClient] Gemini server error (attempt {attempt}/{max_retries}): {exc}\n"
                    f"            Retrying in {wait}s…"
                )
                time.sleep(wait)
            except genai_errors.ClientError as exc:
                # 429 rate-limit — parse retryDelay from the error body if present
                if "429" in str(exc) and attempt < max_retries:
                    match = re.search(r"retry in (\d+)", str(exc), re.IGNORECASE)
                    wait = int(match.group(1)) + 2 if match else retry_delay * attempt
                    print(
                        f"[LLMClient] Rate limit hit (attempt {attempt}/{max_retries}). "
                        f"Retrying in {wait}s…"
                    )
                    time.sleep(wait)
                else:
                    raise

        # Extract reasoning text and the tool call from Gemini's response
        reasoning, tool_name, tool_input = self._parse_response(response)

        # Append Gemini's full response to history so the next call has context
        if response.candidates and response.candidates[0].content:
            self._messages.append(response.candidates[0].content)

        return tool_name, tool_input, reasoning

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_message(
        screenshot_b64: str,
        prev_tool_name: str | None = None,
        prev_tool_result: dict[str, Any] | None = None,
    ) -> types.Content:
        """
        Construct a user message for the next agent turn.
        """
        parts = []

        if prev_tool_name is not None and prev_tool_result is not None:
            parts.append(
                types.Part.from_function_response(
                    name=prev_tool_name,
                    response=prev_tool_result
                )
            )

        parts.append(
            types.Part.from_text(
                text="Here is the current state of the browser. What do you do next?"
            )
        )
        parts.append(
            types.Part.from_bytes(
                data=base64.b64decode(screenshot_b64),
                mime_type="image/png"
            )
        )

        return types.Content(role="user", parts=parts)

    @staticmethod
    def _parse_response(
        response,
    ) -> tuple[str, str, dict[str, Any]]:
        """
        Extract reasoning text and tool-use details from a Gemini response.

        Returns:
            (reasoning, tool_name, tool_input)

        Raises:
            ValueError if no function_call block is found.
        """
        reasoning = ""
        tool_name = None
        tool_input = {}

        if not response.candidates or not response.candidates[0].content:
            raise ValueError(f"Empty response from Gemini: {response}")

        for part in response.candidates[0].content.parts:
            if part.text:
                reasoning += part.text + "\n"
            elif part.function_call:
                tool_name = part.function_call.name
                # args can be accessed directly or converted to a dict
                tool_input = dict(part.function_call.args) if part.function_call.args else {}

        reasoning = reasoning.strip()

        if tool_name is None:
            raise ValueError(
                f"Gemini did not call a tool. Response text: {reasoning!r}"
            )

        return reasoning, tool_name, tool_input
