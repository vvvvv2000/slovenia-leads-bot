"""
audit_websites.py — Audits websites found in results.json.
For each business with a website URL, it:
  1. Detects the platform (WIX, GoDaddy, Squarespace, WordPress, etc.)
  2. Flags specific issues (free domain, no SSL, outdated tech, no mobile, etc.)
  3. Generates a sales pitch snippet for each issue found.
  4. Saves enriched data back to results.json and produces dashboard.html.

Usage:
    python audit_websites.py
"""

import json
import re
import time
import socket
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

RESULTS_FILE = "results.json"
TIMEOUT = 10
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Platform detection rules ────────────────────────────────────────────────
# Each rule: (platform_name, list_of_checks)
# check can be: ("url", substring) | ("html", substring) | ("header", key, value_substring)
PLATFORM_RULES = [
    ("Wix", [
        ("url", "wixsite.com"),
        ("html", 'content="Wix.com"'),
        ("html", "_wix-"),
        ("html", "static.wixstatic.com"),
        ("html", 'name="generator" content="Wix'),
    ]),
    ("GoDaddy Website Builder", [
        ("url", "godaddysites.com"),
        ("url", "godaddy.com"),
        ("html", "GoDaddy"),
        ("html", "godaddy-website-builder"),
        ("html", "secureserver.net"),
    ]),
    ("Squarespace", [
        ("html", 'name="generator" content="Squarespace"'),
        ("html", "squarespace.com"),
        ("html", "static1.squarespace.com"),
    ]),
    ("WordPress", [
        ("html", "/wp-content/"),
        ("html", "/wp-includes/"),
        ("html", 'name="generator" content="WordPress'),
        ("url", "wordpress.com"),
    ]),
    ("Webflow", [
        ("html", "webflow.io"),
        ("html", "<!-- Webflow -->"),
        ("html", "assets.website-files.com"),
    ]),
    ("Weebly", [
        ("url", "weebly.com"),
        ("html", "weeblysite.com"),
        ("html", "editmysite.com"),
    ]),
    ("Jimdo", [
        ("url", "jimdofree.com"),
        ("url", "jimdo.com"),
        ("html", "jimdostatic.com"),
    ]),
    ("Shopify", [
        ("html", "cdn.shopify.com"),
        ("html", "Shopify.theme"),
        ("url", "myshopify.com"),
    ]),
    ("Blogger", [
        ("html", 'content="blogger"'),
        ("url", "blogspot.com"),
    ]),
    ("Joomla", [
        ("html", 'content="Joomla'),
        ("html", "/media/jui/"),
    ]),
    ("Drupal", [
        ("html", 'content="Drupal'),
        ("html", "/sites/default/files/"),
    ]),
]

# ─── Free / low-quality domain patterns ──────────────────────────────────────
FREE_DOMAIN_PATTERNS = [
    r"wixsite\.com",
    r"godaddysites\.com",
    r"weebly\.com",
    r"weeblysite\.com",
    r"jimdo(free)?\.com",
    r"wordpress\.com",
    r"blogspot\.com",
    r"myshopify\.com",
    r"webflow\.io",
    r"squarespace\.com",
    r"mystrikingly\.com",
    r"simplesite\.com",
    r"yolasite\.com",
    r"000webhostapp\.com",
    r"netlify\.app",
    r"github\.io",
    r"pages\.dev",
]

# ─── Issue definitions ────────────────────────────────────────────────────────
# Each issue: (issue_id, label, sales_pitch)
ISSUE_DEFINITIONS = {
    "no_website": (
        "🚫 No website",
        "This business has no website — they're invisible online. "
        "Every day without one means lost customers who search Google first."
    ),
    "no_ssl": (
        "🔓 No HTTPS / SSL",
        "Their site runs on plain HTTP — browsers warn visitors it's 'Not Secure'. "
        "Google penalises non-HTTPS sites in search rankings."
    ),
    "free_domain": (
        "🆓 Free/subdomain URL",
        "Their web address is a free subdomain (e.g. businessname.wixsite.com). "
        "This looks unprofessional and hurts trust — customers expect a real .si or .com domain."
    ),
    "platform_wix": (
        "🏗️ Built on Wix",
        "Wix sites are limited in speed, SEO, and customisation. "
        "A professional custom site would load faster and rank higher on Google."
    ),
    "platform_godaddy": (
        "🏗️ Built on GoDaddy Builder",
        "GoDaddy's website builder produces cookie-cutter sites with poor SEO. "
        "A custom site would stand out and convert more visitors."
    ),
    "platform_squarespace": (
        "🏗️ Built on Squarespace",
        "Squarespace is a template platform — it's generic and has limited SEO control."
    ),
    "platform_weebly": (
        "🏗️ Built on Weebly",
        "Weebly sites are basic drag-and-drop — limited SEO and branding potential."
    ),
    "platform_jimdo": (
        "🏗️ Built on Jimdo",
        "Jimdo free sites display 'Jimdo' branding and score poorly on SEO and speed."
    ),
    "platform_wordpress": (
        "🏗️ Built on WordPress.com",
        "WordPress.com (not .org) free plans show ads and have restricted customisation."
    ),
    "no_mobile": (
        "📱 Not mobile-friendly",
        "Over 60% of web traffic is mobile. Their site lacks a mobile viewport tag — "
        "it will look broken on phones and Google will demote it in mobile search."
    ),
    "outdated_html": (
        "⏳ Outdated HTML/tech",
        "The site uses old HTML standards (pre-HTML5 doctype or legacy meta tags). "
        "An outdated site signals neglect to visitors and search engines."
    ),
    "old_jquery": (
        "⚙️ Outdated jQuery",
        "The site loads an old version of jQuery (pre-3.x) which has known security vulnerabilities."
    ),
    "slow_response": (
        "🐢 Slow server response",
        "The page took over 3 seconds to respond — Google uses page speed as a ranking factor "
        "and slow sites lose 53% of mobile visitors before they even load."
    ),
    "no_favicon": (
        "🖼️ No favicon",
        "No browser icon (favicon) — a small but visible sign of a low-quality or unfinished website."
    ),
    "meta_missing": (
        "🔍 Missing SEO meta description",
        "No meta description found — this is the text Google shows in search results. "
        "Without it, Google generates one randomly, often looking unprofessional."
    ),
    "phone_not_on_site": (
        "📞 Phone number not on website",
        "Their phone number (visible on Google Maps) doesn't appear on their website, "
        "making it harder for visitors to contact them."
    ),
}


def detect_platform(url: str, html: str) -> list[str]:
    """Return list of detected platform names."""
    found = []
    url_lower = url.lower()
    html_lower = html.lower()
    for platform, rules in PLATFORM_RULES:
        for rule in rules:
            if rule[0] == "url" and rule[1] in url_lower:
                found.append(platform)
                break
            elif rule[0] == "html" and rule[1].lower() in html_lower:
                found.append(platform)
                break
    return found


def is_free_domain(url: str) -> bool:
    for pattern in FREE_DOMAIN_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def has_ssl(url: str) -> bool:
    return url.startswith("https://")


def has_mobile_viewport(html: str) -> bool:
    return bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE))


def has_outdated_doctype(html: str) -> bool:
    first_100 = html[:200].strip().lower()
    # Old HTML 4 / XHTML doctypes
    if re.search(r'<!doctype\s+html\s+public\s+"', first_100):
        return True
    # Missing doctype entirely
    if not first_100.startswith("<!doctype"):
        return True
    return False


def has_old_jquery(html: str) -> bool:
    matches = re.findall(r'jquery[.-](\d+)\.(\d+)', html, re.IGNORECASE)
    for major, minor in matches:
        if int(major) < 3:
            return True
    return False


def has_favicon(html: str, soup: BeautifulSoup) -> bool:
    links = soup.find_all("link", rel=lambda r: r and any("icon" in str(i).lower() for i in r))
    return len(links) > 0


def has_meta_description(soup: BeautifulSoup) -> bool:
    tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    return tag is not None and tag.get("content", "").strip() != ""


def phone_on_website(html: str, phone: str) -> bool:
    if not phone:
        return True  # can't check
    # strip non-digits and search
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 6:
        return True
    return digits in re.sub(r'\D', '', html)


def audit_website(biz: dict) -> dict:
    url = biz.get("website", "").strip()
    issues = []
    platforms = []
    audit_note = ""

    if not url:
        source = biz.get("source", "")
        # itis.siol.net listing pages don't include website URLs —
        # absence of a URL here means "unknown", not "no website"
        if source != "itis.siol.net":
            issues.append("no_website")
        biz["audit"] = {
            "issues": issues,
            "platforms": [],
            "audit_note": "No website URL found in directory." if source == "itis.siol.net" else "No website listed.",
            "raw_url": url,
        }
        return biz

    # Ensure scheme
    if not url.startswith("http"):
        url = "https://" + url

    if not has_ssl(url):
        issues.append("no_ssl")

    if is_free_domain(url):
        issues.append("free_domain")

    # Fetch page
    html = ""
    soup = BeautifulSoup("", "html.parser")
    response_time = None
    fetch_error = None

    try:
        start = time.time()
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        response_time = round(time.time() - start, 2)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        final_url = resp.url

        # Re-check SSL after redirect
        if not final_url.startswith("https://"):
            if "no_ssl" not in issues:
                issues.append("no_ssl")
        # Re-check free domain after redirect
        if is_free_domain(final_url) and "free_domain" not in issues:
            issues.append("free_domain")

    except requests.exceptions.SSLError:
        issues.append("no_ssl")
        fetch_error = "SSL error"
    except requests.exceptions.ConnectionError:
        fetch_error = "Connection refused / DNS failure"
        issues.append("no_website")
    except requests.exceptions.Timeout:
        fetch_error = "Timed out"
        issues.append("slow_response")
    except Exception as e:
        fetch_error = str(e)[:80]

    if response_time and response_time > 3.0:
        issues.append("slow_response")

    if html:
        platforms = detect_platform(url, html)

        # Map platform to issue key
        platform_issue_map = {
            "Wix": "platform_wix",
            "GoDaddy Website Builder": "platform_godaddy",
            "Squarespace": "platform_squarespace",
            "Weebly": "platform_weebly",
            "Jimdo": "platform_jimdo",
            "WordPress": "platform_wordpress",
        }
        for p in platforms:
            key = platform_issue_map.get(p)
            if key and key not in issues:
                issues.append(key)

        if not has_mobile_viewport(html):
            issues.append("no_mobile")
        if has_outdated_doctype(html):
            issues.append("outdated_html")
        if has_old_jquery(html):
            issues.append("old_jquery")
        if not has_favicon(html, soup):
            issues.append("no_favicon")
        if not has_meta_description(soup):
            issues.append("meta_missing")
        if not phone_on_website(html, biz.get("phone", "")):
            issues.append("phone_not_on_site")

    audit_note = fetch_error or f"Loaded in {response_time}s" if response_time else ""

    biz["audit"] = {
        "issues": issues,
        "platforms": platforms,
        "audit_note": audit_note,
        "raw_url": url,
        "response_time": response_time,
    }
    return biz


def main():
    path = Path(RESULTS_FILE)
    if not path.exists():
        print(f"❌ {RESULTS_FILE} not found. Run maps_scraper.py first.")
        return

    with open(path, encoding="utf-8") as f:
        businesses = json.load(f)

    total = len(businesses)
    print(f"\n🔍 Auditing {total} businesses...\n")

    for i, biz in enumerate(businesses):
        name = biz.get("name", "Unknown")
        website = biz.get("website", "")
        print(f"  [{i+1}/{total}] {name[:40]:40s} | {website[:50] or '(no website)'}")
        businesses[i] = audit_website(biz)
        time.sleep(0.5)  # be polite

    with open(path, "w", encoding="utf-8") as f:
        json.dump(businesses, f, ensure_ascii=False, indent=2)

    # Summary stats
    has_issues = sum(1 for b in businesses if b.get("audit", {}).get("issues"))
    no_web = sum(1 for b in businesses if "no_website" in b.get("audit", {}).get("issues", []))
    print(f"\n✅ Audit complete.")
    print(f"   {has_issues}/{total} businesses have at least one issue.")
    print(f"   {no_web} have no website at all.")
    print(f"\n   Saved → {RESULTS_FILE}")
    print("   Run: python build_dashboard.py\n")

    # Expose issue definitions for the dashboard builder
    return ISSUE_DEFINITIONS


ISSUE_DEFS_EXPORT = ISSUE_DEFINITIONS  # imported by build_dashboard.py

if __name__ == "__main__":
    main()
