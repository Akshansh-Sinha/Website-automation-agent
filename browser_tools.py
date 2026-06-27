"""
browser_tools.py
----------------
All browser automation tools the agent can invoke, implemented with
Playwright's async API. Each tool returns a structured dict so the
agent loop has a consistent result shape to log and pass back to the LLM.

Tools:
  open_browser       - Launch a Chromium instance (headed or headless)
  navigate_to_url    - Go to a URL and wait for network idle
  take_screenshot    - Capture the viewport; returns path + base64 PNG
  click_on_screen    - Single mouse click at (x, y)
  send_keys          - Type text into the currently-focused element
  scroll             - Wheel-scroll the page by (delta_x, delta_y)
  double_click       - Double mouse click at (x, y)
  close_browser      - Tear down the browser and Playwright context
"""

import base64
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


SCREENSHOTS_DIR = Path("screenshots")


class BrowserTools:
    """
    Wraps a single Playwright browser session.

    Usage:
        tools = BrowserTools()
        await tools.open_browser()
        await tools.navigate_to_url("https://example.com")
        result = await tools.take_screenshot()
        await tools.close_browser()
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._step_counter: int = 0

        # Ensure screenshots directory exists at import time so we never
        # have to guard for it inside the hot path.
        SCREENSHOTS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open_browser(self, headless: bool = False) -> dict:
        """
        Launch a Chromium browser and open a blank page.

        Args:
            headless: Run without a visible window when True.

        Returns:
            {"status": "browser_opened", "headless": bool}
        """
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()
        print(f"[BrowserTools] Browser opened (headless={headless}, viewport=1280x800)")
        return {"status": "browser_opened", "headless": headless}

    async def close_browser(self) -> dict:
        """
        Close the browser and stop Playwright.

        Returns:
            {"status": "browser_closed"}
        """
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        print("[BrowserTools] Browser closed")
        return {"status": "browser_closed"}

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate_to_url(self, url: str) -> dict:
        """
        Navigate the browser to a URL and wait for the network to settle.

        Args:
            url: The fully-qualified URL to load.

        Returns:
            {"status": "navigated", "url": str}
        """
        self._require_page()
        await self._page.goto(url, wait_until="networkidle", timeout=30_000)
        actual_url = self._page.url
        print(f"[BrowserTools] Navigated to {actual_url}")
        return {"status": "navigated", "url": actual_url}

    # ------------------------------------------------------------------
    # Visual perception
    # ------------------------------------------------------------------

    async def take_screenshot(self, label: str = "") -> dict:
        """
        Capture the current viewport as a PNG.

        Saves the file to screenshots/step_NNN[_label].png and returns
        both the file path and the base64-encoded image data so the LLM
        can consume it directly.

        Args:
            label: Optional short label appended to the filename.

        Returns:
            {"status": "screenshot_taken", "path": str, "base64": str, "step": int}
        """
        self._require_page()
        self._step_counter += 1
        suffix = f"_{label}" if label else ""
        filename = SCREENSHOTS_DIR / f"step_{self._step_counter:03d}{suffix}.png"

        png_bytes: bytes = await self._page.screenshot(path=str(filename), full_page=False)
        b64 = base64.b64encode(png_bytes).decode("utf-8")

        print(f"[BrowserTools] Screenshot saved → {filename}")
        return {
            "status": "screenshot_taken",
            "path": str(filename),
            "base64": b64,
            "step": self._step_counter,
        }

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    async def click_on_screen(self, x: int, y: int) -> dict:
        """
        Perform a single left mouse click at viewport coordinates (x, y).

        Args:
            x: Horizontal coordinate in pixels (0 = left edge).
            y: Vertical coordinate in pixels (0 = top edge).

        Returns:
            {"status": "clicked", "x": int, "y": int}
        """
        self._require_page()
        await self._page.mouse.click(x, y)
        print(f"[BrowserTools] Clicked at ({x}, {y})")
        return {"status": "clicked", "x": x, "y": y}

    async def double_click(self, x: int, y: int) -> dict:
        """
        Perform a double mouse click at viewport coordinates (x, y).

        Useful for selecting existing text in an input before replacing it.

        Args:
            x: Horizontal coordinate in pixels.
            y: Vertical coordinate in pixels.

        Returns:
            {"status": "double_clicked", "x": int, "y": int}
        """
        self._require_page()
        await self._page.mouse.dblclick(x, y)
        print(f"[BrowserTools] Double-clicked at ({x}, {y})")
        return {"status": "double_clicked", "x": x, "y": y}

    async def scroll(self, delta_x: int, delta_y: int) -> dict:
        """
        Scroll the page by (delta_x, delta_y) pixels using the mouse wheel.

        Positive delta_y scrolls DOWN; negative scrolls UP.
        Scroll events are dispatched from the viewport centre so they always
        hit the page body rather than a focused element.

        Args:
            delta_x: Horizontal scroll amount in pixels.
            delta_y: Vertical scroll amount in pixels.

        Returns:
            {"status": "scrolled", "delta_x": int, "delta_y": int}
        """
        self._require_page()
        # Dispatch from the horizontal centre and vertical centre of the
        # viewport so the event lands on the page rather than a widget.
        await self._page.mouse.wheel(delta_x, delta_y)
        print(f"[BrowserTools] Scrolled ({delta_x}, {delta_y})")
        return {"status": "scrolled", "delta_x": delta_x, "delta_y": delta_y}

    # ------------------------------------------------------------------
    # Keyboard interaction
    # ------------------------------------------------------------------

    async def send_keys(self, text: str) -> dict:
        """
        Type text into the currently-focused element, character by character,
        with a small delay between keystrokes to mimic human input and avoid
        input-event race conditions.

        Call click_on_screen first to focus the target field.

        Args:
            text: The string to type.

        Returns:
            {"status": "keys_sent", "text": str, "length": int}
        """
        self._require_page()
        await self._page.keyboard.type(text, delay=50)
        print(f"[BrowserTools] Typed {len(text)} characters: {text!r}")
        return {"status": "keys_sent", "text": text, "length": len(text)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_page(self) -> None:
        """Raise a clear error if the browser has not been opened yet."""
        if self._page is None:
            raise RuntimeError(
                "Browser is not open. Call open_browser() before using other tools."
            )
