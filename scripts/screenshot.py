#!/usr/bin/env python3
"""Take a screenshot of an OpenNMS URL and save it to the docs/screenshots/ folder.

Supports optional OpenNMS login so authenticated pages (Geo Map, events, node lists)
can be captured. Use --wait to allow slow-rendering pages enough time to finish
loading before the screenshot is taken.
"""

import argparse
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


def screenshot(
    url: str,
    name: str | None = None,
    wait: int = 5000,
    user: str | None = None,
    password: str | None = None,
    base_url: str = "http://localhost:8980",
    width: int = 1280,
    height: int = 900,
) -> Path:
    out_dir = Path(__file__).parent.parent / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = name or datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"{slug}.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})

        if user and password:
            login_url = f"{base_url}/opennms/login.jsp"
            page.goto(login_url, wait_until="networkidle", timeout=15000)
            page.fill("input[name='j_username']", user)
            page.fill("input[name='j_password']", password)
            page.click("button[type='submit']")
            page.wait_for_url(f"{base_url}/**", timeout=10000)
            page.wait_for_timeout(1500)
            # Dismiss first-login "Change Password" dialog if present
            skip_btn = page.query_selector("button:has-text('Skip')")
            if skip_btn:
                skip_btn.click()
                page.wait_for_timeout(500)

        page.goto(url, wait_until="networkidle", timeout=30000)
        if wait:
            page.wait_for_timeout(wait)
        page.screenshot(path=str(dest), full_page=False)
        browser.close()

    print(dest)
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screenshot an OpenNMS URL into docs/screenshots/")
    parser.add_argument("url", help="URL to capture")
    parser.add_argument("--name", help="Output filename stem (default: timestamp)")
    parser.add_argument("--wait", type=int, default=5000,
                        help="Extra wait ms after page load (default: 5000)")
    parser.add_argument("--user", help="OpenNMS username for login (e.g. admin)")
    parser.add_argument("--password", help="OpenNMS password for login (e.g. admin)")
    parser.add_argument("--base-url", default="http://localhost:8980",
                        help="OpenNMS base URL (default: http://localhost:8980)")
    parser.add_argument("--width", type=int, default=1280,
                        help="Viewport width in pixels (default: 1280)")
    parser.add_argument("--height", type=int, default=900,
                        help="Viewport height in pixels (default: 900)")
    args = parser.parse_args()
    screenshot(args.url, args.name, args.wait, args.user, args.password, args.base_url,
               args.width, args.height)
