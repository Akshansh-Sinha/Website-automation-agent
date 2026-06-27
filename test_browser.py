"""
test_browser.py
---------------
Smoke test for all BrowserTools methods — no API key required.

Runs every tool against the real target URL in sequence and prints a
PASS / FAIL result for each one.  If everything passes you know the
Playwright setup is correct and the agent is ready to run.

Usage:
    python test_browser.py
"""

import asyncio
import sys

from browser_tools import BrowserTools


TARGET_URL = "https://ui.shadcn.com/docs/forms/react-hook-form"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(label: str, result: dict, expected_key: str, expected_value=None) -> bool:
    ok = expected_key in result
    if ok and expected_value is not None:
        ok = result[expected_key] == expected_value
    status = PASS if ok else FAIL
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         got: {result}")
    return ok


async def run_tests() -> int:
    """Run all tool tests. Returns number of failures."""
    tools = BrowserTools()
    failures = 0

    print("\n=== BrowserTools smoke test ===\n")

    # ── open_browser ──────────────────────────────────────────────────
    print("1. open_browser")
    try:
        result = await tools.open_browser(headless=True)   # headless for CI / speed
        if not check("returns status=browser_opened", result, "status", "browser_opened"):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] open_browser raised: {exc}")
        failures += 1
        return failures   # can't continue without a browser

    # ── navigate_to_url ───────────────────────────────────────────────
    print("\n2. navigate_to_url")
    try:
        result = await tools.navigate_to_url(TARGET_URL)
        if not check("returns status=navigated", result, "status", "navigated"):
            failures += 1
        if not check("url contains shadcn", result, "url"):
            failures += 1
        else:
            ok = "shadcn" in result["url"] or "react-hook-form" in result["url"]
            status = PASS if ok else FAIL
            print(f"  [{status}] url is correct shadcn page")
            if not ok:
                failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] navigate_to_url raised: {exc}")
        failures += 1

    # ── take_screenshot ───────────────────────────────────────────────
    print("\n3. take_screenshot")
    try:
        result = await tools.take_screenshot(label="test")
        if not check("returns status=screenshot_taken", result, "status", "screenshot_taken"):
            failures += 1
        if not check("has base64 field", result, "base64"):
            failures += 1
        else:
            b64_ok = len(result["base64"]) > 1000   # a real PNG is never tiny
            status = PASS if b64_ok else FAIL
            print(f"  [{status}] base64 data is non-trivial ({len(result['base64'])} chars)")
            if not b64_ok:
                failures += 1
        if not check("has path field", result, "path"):
            failures += 1
        else:
            import os
            path_ok = os.path.exists(result["path"])
            status = PASS if path_ok else FAIL
            print(f"  [{status}] file written to disk: {result['path']}")
            if not path_ok:
                failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] take_screenshot raised: {exc}")
        failures += 1

    # ── scroll ────────────────────────────────────────────────────────
    print("\n4. scroll")
    try:
        result = await tools.scroll(delta_x=0, delta_y=400)
        if not check("returns status=scrolled", result, "status", "scrolled"):
            failures += 1
        if not check("delta_y echoed back", result, "delta_y", 400):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] scroll raised: {exc}")
        failures += 1

    # ── click_on_screen ───────────────────────────────────────────────
    print("\n5. click_on_screen")
    try:
        result = await tools.click_on_screen(x=640, y=400)
        if not check("returns status=clicked", result, "status", "clicked"):
            failures += 1
        if not check("x echoed back", result, "x", 640):
            failures += 1
        if not check("y echoed back", result, "y", 400):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] click_on_screen raised: {exc}")
        failures += 1

    # ── double_click ──────────────────────────────────────────────────
    print("\n6. double_click")
    try:
        result = await tools.double_click(x=640, y=400)
        if not check("returns status=double_clicked", result, "status", "double_clicked"):
            failures += 1
        if not check("x echoed back", result, "x", 640):
            failures += 1
        if not check("y echoed back", result, "y", 400):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] double_click raised: {exc}")
        failures += 1

    # ── send_keys ─────────────────────────────────────────────────────
    print("\n7. send_keys")
    try:
        result = await tools.send_keys("hello")
        if not check("returns status=keys_sent", result, "status", "keys_sent"):
            failures += 1
        if not check("text echoed back", result, "text", "hello"):
            failures += 1
        if not check("length correct", result, "length", 5):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] send_keys raised: {exc}")
        failures += 1

    # ── close_browser ─────────────────────────────────────────────────
    print("\n8. close_browser")
    try:
        result = await tools.close_browser()
        if not check("returns status=browser_closed", result, "status", "browser_closed"):
            failures += 1
    except Exception as exc:
        print(f"  [{FAIL}] close_browser raised: {exc}")
        failures += 1

    # ── Summary ───────────────────────────────────────────────────────
    print()
    print("=" * 40)
    if failures == 0:
        print(f"  {PASS}  All browser tools working.")
        print("  You can now run: python agent.py")
    else:
        print(f"  {FAIL}  {failures} check(s) failed.")
        print("  Fix the issues above before running the full agent.")
    print("=" * 40)
    print()

    return failures


if __name__ == "__main__":
    failures = asyncio.run(run_tests())
    sys.exit(0 if failures == 0 else 1)
