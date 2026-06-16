"""
maps_scraper.py — Scrapes Google Maps for businesses in Slovenia.
Extracts: name, address, phone, website URL, rating, review count.
Saves results to results.json for the website auditor.

Usage:
    python maps_scraper.py --query "restaurants" --location "Ljubljana, Slovenia" --max 50
"""

import asyncio
import json
import argparse
import time
import random
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

OUTPUT_FILE = "results.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--query", default="restavracije", help="Search term (e.g. 'restaurants', 'plumbers')")
    p.add_argument("--location", default="Ljubljana, Slovenija", help="Location to search in")
    p.add_argument("--max", type=int, default=50, help="Max businesses to scrape")
    p.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    return p.parse_args()


async def scroll_to_load(page, container_selector, max_scrolls=20):
    """Scroll the results panel to load more listings."""
    for i in range(max_scrolls):
        await page.evaluate(f"""
            const el = document.querySelector('{container_selector}');
            if (el) el.scrollTop = el.scrollHeight;
        """)
        await asyncio.sleep(random.uniform(1.2, 2.0))

        # Check if "end of results" marker appears
        end_text = await page.query_selector('text="You\'ve reached the end of the list"')
        if end_text:
            break


async def extract_listings(page):
    """Extract all visible listing links from the results panel."""
    links = await page.query_selector_all('a[href*="/maps/place/"]')
    hrefs = set()
    for link in links:
        href = await link.get_attribute("href")
        if href and "/maps/place/" in href:
            hrefs.add(href)
    return list(hrefs)


async def scrape_listing(page, url):
    """Visit a single Google Maps listing and extract business details."""
    business = {
        "name": "",
        "address": "",
        "phone": "",
        "website": "",
        "rating": "",
        "reviews": "",
        "category": "",
        "maps_url": url,
    }

    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # Name
        try:
            name_el = await page.query_selector('h1')
            if name_el:
                business["name"] = (await name_el.inner_text()).strip()
        except Exception:
            pass

        # Rating
        try:
            rating_el = await page.query_selector('div[jsaction*="pane.rating"]')
            if rating_el:
                text = (await rating_el.inner_text()).strip()
                match = re.search(r'(\d[\d,\.]+)', text)
                if match:
                    business["rating"] = match.group(1).replace(",", ".")
        except Exception:
            pass

        # Reviews count — look for text like "(123)"
        try:
            page_text = await page.inner_text('body')
            m = re.search(r'\((\d[\d,]+)\)', page_text)
            if m:
                business["reviews"] = m.group(1).replace(",", "")
        except Exception:
            pass

        # Category
        try:
            cat_el = await page.query_selector('button[jsaction*="category"]')
            if cat_el:
                business["category"] = (await cat_el.inner_text()).strip()
        except Exception:
            pass

        # Address — aria-label often works reliably
        try:
            addr_el = await page.query_selector('[data-item-id="address"]')
            if not addr_el:
                addr_el = await page.query_selector('[aria-label*="Address"]')
            if addr_el:
                business["address"] = (await addr_el.inner_text()).strip()
        except Exception:
            pass

        # Phone
        try:
            phone_el = await page.query_selector('[data-item-id*="phone"]')
            if not phone_el:
                phone_el = await page.query_selector('[aria-label*="Phone"]')
            if phone_el:
                business["phone"] = (await phone_el.inner_text()).strip()
        except Exception:
            pass

        # Website
        try:
            web_el = await page.query_selector('a[data-item-id="authority"]')
            if not web_el:
                web_el = await page.query_selector('[aria-label*="Website"]')
            if web_el:
                href = await web_el.get_attribute("href")
                if href:
                    business["website"] = href.strip()
        except Exception:
            pass

    except PlaywrightTimeout:
        print(f"  [timeout] {url[:60]}")
    except Exception as e:
        print(f"  [error] {url[:60]} — {e}")

    return business


async def main():
    args = parse_args()
    search_query = f"{args.query} {args.location}"
    print(f"\n🗺  Searching Google Maps: '{search_query}'")
    print(f"   Max results: {args.max} | Headless: {args.headless}\n")

    businesses = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # --- Search ---
        search_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}/"
        await page.goto(search_url, timeout=30000, wait_until="networkidle")
        await asyncio.sleep(2)

        # Accept cookies if prompted
        try:
            for btn_text in ["Accept all", "Alle akzeptieren", "Sprejmi vse", "I agree"]:
                btn = await page.query_selector(f'button:has-text("{btn_text}")')
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except Exception:
            pass

        # Scroll to load more listings
        panel_selector = 'div[role="feed"]'
        print("  Scrolling results to load listings...")
        await scroll_to_load(page, panel_selector, max_scrolls=30)

        all_links = await extract_listings(page)
        print(f"  Found {len(all_links)} listing links. Visiting up to {args.max}...\n")

        for i, link in enumerate(all_links[: args.max]):
            print(f"  [{i+1}/{min(len(all_links), args.max)}] Scraping listing...")
            biz = await scrape_listing(page, link)
            if biz["name"]:
                businesses.append(biz)
                print(f"    ✓ {biz['name']} | website: {biz['website'] or '—'}")
            await asyncio.sleep(random.uniform(1.0, 2.0))

        await browser.close()

    # Save raw data
    out_path = Path(OUTPUT_FILE)
    existing = []
    if out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)

    # Merge by maps_url to avoid dupes
    existing_urls = {b["maps_url"] for b in existing}
    new_entries = [b for b in businesses if b["maps_url"] not in existing_urls]
    combined = existing + new_entries

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(new_entries)} new businesses ({len(combined)} total) → {OUTPUT_FILE}")
    print("   Run: python audit_websites.py\n")


if __name__ == "__main__":
    asyncio.run(main())
