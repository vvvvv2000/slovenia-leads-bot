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
    """Parse one itis results page → list of business dicts.

    itis.siol.net is ASP.NET WebForms — business name links use __doPostBack,
    so there are no plain <a href> links on the listing page for individual entries.
    Instead we parse the page's full text, which is split into blocks by the
    "Shrani" (Save) button that precedes every listing card.

    Each block looks like:
        [optional ad description]
        BUSINESS NAME                         ← ALL CAPS
        Gostilne in restavracije              ← category
        TELEFON (prikaz vseh številk)         ← literal marker
        041 220 815                           ← phone
        EMAIL@DOMAIN.SI                       ← optional
        Street name 5, City                   ← address street
        1234 City                             ← postal code + city
    """
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)

    businesses = []

    # Split into blocks at "Shrani" — one block per listing card
    blocks = re.split(r'\bShrani\b', full_text)

    # blocks[0] = page header/nav; blocks[1:] = individual business cards
    for block in blocks[1:]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        biz = {"source": "itis.siol.net"}

        # Find the "TELEFON" line — it separates name/category from contact info
        telefon_idx = next(
            (i for i, l in enumerate(lines) if "TELEFON" in l.upper()), -1
        )

        if telefon_idx > 0:
            pre = lines[:telefon_idx]
            # Business names on itis are always ALL CAPS — prefer those over ad text
            for line in pre:
                stripped = line.strip()
                if len(stripped) > 3 and stripped == stripped.upper() and re.search(r'[A-Z]', stripped):
                    biz["name"] = stripped
                    break
            # Fallback: first line that doesn't look like an ad description
            if not biz.get("name"):
                for line in pre:
                    if len(line) > 3 and not re.search(r'\bv\b|\bin\b|\bna\b|\biz\b|\bje\b', line, re.I):
                        biz["name"] = line
                        break
            if not biz.get("name") and pre:
                biz["name"] = pre[0]
            # Category is typically the last line before TELEFON
            if len(pre) >= 2:
                biz["category"] = pre[-1]
            post = lines[telefon_idx + 1:]
        else:
            # No TELEFON marker — skip (likely not a real listing block)
            continue

        # ── Phone ──────────────────────────────────────────────────────
        for line in post:
            # Slovenian numbers: 01 234 56 78 / 041 220 815 / +386 41 ...
            if re.match(r'^[\+\d][\d\s]{5,}$', line):
                biz["phone"] = re.sub(r'\s+', ' ', line).strip()
                break

        # ── Email ──────────────────────────────────────────────────────
        post_text = " ".join(post)
        em = re.search(r'[\w.+\-]+@[\w\-]+\.[A-Za-z]{2,}', post_text)
        if em:
            biz["email"] = em.group(0)

        # ── Address ────────────────────────────────────────────────────
        # Look for a 4-digit Slovenian postal code line
        for i, line in enumerate(post):
            if re.match(r'^\d{4}\s+\S', line):
                street = post[i - 1] if i > 0 else ""
                # Don't use phone or category as street
                if (street and street != biz.get("phone", "")
                        and not re.match(r'^[\d\s\+]{6,}$', street)):
                    biz["address"] = f"{street}, {line}"
                else:
                    biz["address"] = line
                break

        if biz.get("name") and len(biz["name"]) > 3:
            # Stop at pagination markers
            if biz["name"] in ("Naprej", "Nazaj", "Zacetek", "Konec"):
                continue
            businesses.append(biz)

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

        print(f"  Found {len(listings)} listings on page {page}.")

        for i, biz in enumerate(listings):
            biz.setdefault("source", "itis.siol.net")
            biz.setdefault("maps_url", url)
            print(f"    [{i+1}/{len(listings)}] {biz.get('name','?')[:50]}")
            results.append(biz)

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
            print("Provide --query for bizi source. Example: --query restavracija")
            return
        data = scrape_bizi(query=args.query, max_pages=args.pages)
    else:
        print("Unknown source.")
        return

    save_results(data)


if __name__ == "__main__":
    main()
