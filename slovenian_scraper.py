"""
slovenian_scraper.py — Scrapes Slovenian business directories for leads.

Supported sources:
  1. itis.siol.net  — Slovenia's phone book, organized by category & city (FREE, no login needed)
  2. bizi.si        — Business registry with website URLs (public pages, no login for basics)

Output: appends to results.json (same format as maps_scraper.py)

Usage examples:
    # Scrape restaurants from itis.siol.net
    python slovenian_scraper.py --source itis --category "Gostilne-in-restavracije" --pages 5

    # Scrape by city
    python slovenian_scraper.py --source itis --city "Ljubljana" --pages 3

    # Scrape a specific category from bizi.si
    python slovenian_scraper.py --source bizi --query "restavracija" --pages 3

Available itis.siol.net categories (use exact slug):
    Gostilne-in-restavracije, Picerije-in-spageterije, Bar, Hoteli, Turizem,
    Avtoservis, Frizerska-dejavnost, Kozmeticna-dejavnost, Gradbeništvo,
    Nepremicnine, Racunovodstvo-in-knjigovodstvo, Trgovina, Zdravstvo,
    Zobozdravstvo, Fitnes-in-skupinske-vadbe  ...and many more (see itis.siol.net)
"""

import argparse
import json
import time
import random
import re
from pathlib import Path
from urllib.parse import urljoin, quote, unquote
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "results.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
    "Referer": "https://itis.siol.net/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ─────────────────────────────────────────────────────────────
#  itis.siol.net
# ─────────────────────────────────────────────────────────────

def itis_listing_url(category=None, city=None, page=1):
    """Build itis.siol.net search URL."""
    if category:
        base = f"https://itis.siol.net/dejavnost/{quote(category, safe='-')}"
    elif city:
        base = f"https://itis.siol.net/kraj/{quote(city, safe=' ')}"
    else:
        base = "https://itis.siol.net/"
    if page > 1:
        base += f"/stran-{page}"
    return base


def itis_parse_listing_page(html: str) -> list[dict]:
    """Parse one itis results page → list of {name, phone, address, category, detail_url}."""
    soup = BeautifulSoup(html, "html.parser")
    businesses = []

    # Each business is inside a div that contains a bold name and a phone number
    # Structure: div.result-list-item (or similar) with heading link
    # The links to individual business pages look like: /BUSINESS-NAME?ID
    for card in soup.select("div.result-list-item, div[class*='result']"):
        biz = {}

        # Name + detail link
        name_el = card.select_one("strong a, h2 a, .result-name a")
        if name_el:
            biz["name"] = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            if href:
                biz["detail_url"] = urljoin("https://itis.siol.net", href)

        # Phone — first visible phone number
        phone_el = card.select_one("[class*='phone'], [class*='tel']")
        if phone_el:
            biz["phone"] = phone_el.get_text(strip=True)

        # Address
        addr_el = card.select_one("[class*='address'], [class*='addr']")
        if addr_el:
            biz["address"] = addr_el.get_text(strip=True)

        # Category
        cat_el = card.select_one("[class*='category'], [class*='dejavnost']")
        if cat_el:
            biz["category"] = cat_el.get_text(strip=True)

        if biz.get("name"):
            businesses.append(biz)

    # Fallback: if the CSS selectors above don't match, try a text-based parse
    if not businesses:
        businesses = itis_parse_listing_fallback(soup)

    return businesses


def itis_parse_listing_fallback(soup: BeautifulSoup) -> list[dict]:
    """Fallback parser: extract business cards by looking for phone patterns."""
    businesses = []

    # itis renders each entry in a block with the name as a bold anchor
    # and the phone in a span. We'll look for anchors that link to business pages.
    for link in soup.select('a[href*="?"]'):
        href = link.get("href", "")
        # Business pages have numeric IDs like /BUSINESS-NAME?12345678
        if not re.search(r'\?\d{5,}$', href):
            continue
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        parent = link.find_parent()
        if not parent:
            continue

        # Walk up to find the enclosing card
        card_text = ""
        el = parent
        for _ in range(5):
            if el is None:
                break
            card_text = el.get_text(" ", strip=True)
            # A card usually contains at least a phone-like pattern
            if re.search(r'\d{2}\s*\d{3}\s*\d{2}', card_text):
                break
            el = el.find_parent()

        # Extract phone
        phone_match = re.search(r'(?:0[1-9]\d[\s\d]{6,})', card_text)
        phone = phone_match.group(0).strip() if phone_match else ""

        businesses.append({
            "name": name,
            "phone": phone,
            "detail_url": urljoin("https://itis.siol.net", href),
        })

    return businesses


def itis_parse_business_page(html: str, url: str) -> dict:
    """Parse individual itis business page to get website, email, address."""
    soup = BeautifulSoup(html, "html.parser")
    info = {"website": "", "email": "", "address": "", "phone": "", "category": ""}

    # Website link — itis shows it as an external link with a globe icon or label 'Splet'
    for a in soup.select("a[href^='http']"):
        href = a.get("href", "")
        # Skip itis-internal and common tracking links
        if any(skip in href for skip in ["itis.siol.net", "siol.net", "google.com",
                                          "facebook.com", "instagram.com",
                                          "googletagmanager", "StatsUpdate"]):
            continue
        text = a.get_text(strip=True).lower()
        parent_text = (a.find_parent() or a).get_text(strip=True).lower()
        if any(kw in parent_text for kw in ["splet", "www", "spletna", "web", ".si", ".com"]):
            info["website"] = href
            break

    # Broader fallback: any external link
    if not info["website"]:
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            if any(skip in href for skip in ["itis.siol.net", "siol.net", "google.com",
                                              "facebook.com", "instagram.com",
                                              "googletagmanager", "StatsUpdate",
                                              "bizi.si", "najdi.si", "tsmedia"]):
                continue
            info["website"] = href
            break

    # Email
    for a in soup.select("a[href^='mailto:']"):
        info["email"] = a.get("href", "").replace("mailto:", "").strip()
        break

    full_text = soup.get_text(" ", strip=True)

    # Phone — grab first match
    phone_match = re.search(r'(?:\+386\s?|0)(?:\d[\s\d]{6,12})', full_text)
    if phone_match:
        info["phone"] = re.sub(r'\s+', ' ', phone_match.group(0)).strip()

    # Address
    for sel in ["[class*='address']", "[class*='addr']", "span.adr", ".vcard .adr"]:
        el = soup.select_one(sel)
        if el:
            info["address"] = el.get_text(" ", strip=True)
            break

    return info


def scrape_itis(category=None, city=None, max_pages=5):
    """Scrape itis.siol.net for a given category or city."""
    results = []
    print(f"\n🇸🇮 Scraping itis.siol.net | category={category or '—'} city={city or '—'} | max_pages={max_pages}")

    for page in range(1, max_pages + 1):
        url = itis_listing_url(category=category, city=city, page=page)
        print(f"  Page {page}: {url}")
        try:
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [error] {e}")
            break

        listings = itis_parse_listing_page(resp.text)
        if not listings:
            print(f"  No listings found on page {page} — stopping.")
            break

        print(f"  Found {len(listings)} listings on page {page}. Fetching details...")

        for i, biz in enumerate(listings):
            detail_url = biz.pop("detail_url", "")
            if detail_url:
                try:
                    detail_resp = SESSION.get(detail_url, timeout=12)
                    extra = itis_parse_business_page(detail_resp.text, detail_url)
                    biz.update({k: v for k, v in extra.items() if v and not biz.get(k)})
                    biz["source"] = "itis.siol.net"
                    biz["maps_url"] = detail_url
                except Exception as e:
                    print(f"    [detail error] {biz.get('name', '?')} — {e}")
            else:
                biz["source"] = "itis.siol.net"
                biz["maps_url"] = url

            print(f"    [{i+1}/{len(listings)}] {biz.get('name','?')[:40]} | {biz.get('website','—')[:40]}")
            results.append(biz)
            time.sleep(random.uniform(0.6, 1.2))

        time.sleep(random.uniform(1.0, 2.0))

    return results


# ─────────────────────────────────────────────────────────────
#  bizi.si
# ─────────────────────────────────────────────────────────────

def scrape_bizi(query: str, max_pages=3):
    """Scrape bizi.si search results for a keyword."""
    results = []
    print(f"\n🏢 Scraping bizi.si | query='{query}' | max_pages={max_pages}")

    for page in range(1, max_pages + 1):
        url = f"https://www.bizi.si/iskanje/?q={quote(query)}&page={page}"
        print(f"  Page {page}: {url}")
        try:
            resp = SESSION.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [error] {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        # bizi result cards
        cards = soup.select(".company-list-item, .result-item, article.company")
        if not cards:
            # Try looser selector
            cards = soup.select("li.search-result, div.company")

        if not cards:
            print(f"  No cards found on page {page} — stopping.")
            break

        print(f"  Found {len(cards)} cards on page {page}")

        for card in cards:
            biz = {"source": "bizi.si"}

            # Name + link
            name_el = card.select_one("a.company-name, h2 a, h3 a, strong a")
            if name_el:
                biz["name"] = name_el.get_text(strip=True)
                href = name_el.get("href", "")
                biz["maps_url"] = urljoin("https://www.bizi.si", href)

            # Website
            web_el = card.select_one("a[href^='http']:not([href*='bizi.si'])")
            if web_el:
                biz["website"] = web_el.get("href", "")

            # Phone
            phone_el = card.select_one("[class*='phone'], [class*='tel']")
            if phone_el:
                biz["phone"] = phone_el.get_text(strip=True)

            # Address
            addr_el = card.select_one("[class*='address'], [class*='addr']")
            if addr_el:
                biz["address"] = addr_el.get_text(strip=True)

            if biz.get("name"):
                results.append(biz)

        time.sleep(random.uniform(1.0, 2.0))

    return results


# ─────────────────────────────────────────────────────────────
#  Save / merge
# ─────────────────────────────────────────────────────────────

def save_results(new_entries: list[dict]):
    path = Path(OUTPUT_FILE)
    existing = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)

    # Deduplicate by name+address
    existing_keys = {(b.get("name",""), b.get("address","")) for b in existing}
    fresh = [b for b in new_entries if (b.get("name",""), b.get("address","")) not in existing_keys]
    combined = existing + fresh

    with open(path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Added {len(fresh)} new entries ({len(combined)} total) → {OUTPUT_FILE}")
    print("   Next step: python audit_websites.py\n")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["itis", "bizi"], default="itis",
                   help="Which directory to scrape")
    p.add_argument("--category", default="",
                   help="[itis] Category slug, e.g. 'Gostilne-in-restavracije'")
    p.add_argument("--city", default="",
                   help="[itis] City name, e.g. 'Ljubljana'")
    p.add_argument("--query", default="",
                   help="[bizi] Search keyword, e.g. 'restavracija'")
    p.add_argument("--pages", type=int, default=5,
                   help="Max pages to scrape (default 5, each page ~30 listings)")
    return p.parse_args()


def main():
    args = parse_args()

    if args.source == "itis":
        if not args.category and not args.city:
            print("⚠️  Provide --category or --city for itis source.")
            print("   Example: --category Gostilne-in-restavracije")
            print("   Example: --city Ljubljana")
            return
        data = scrape_itis(
            category=args.category or None,
            city=args.city or None,
            max_pages=args.pages,
        )
    elif args.source == "bizi":
        if not args.query:
            print("⚠️  Provide --query for bizi source. Example: --query 'restavracija'")
            return
        data = scrape_bizi(query=args.query, max_pages=args.pages)
    else:
        print("Unknown source.")
        return

    save_results(data)


if __name__ == "__main__":
    main()
