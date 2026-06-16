# 🇸🇮 Slovenia Website Lead Bot

A 3-step pipeline that finds local Slovenian businesses, audits their websites, and shows you a filterable sales dashboard.

---

## Quick Start

### 1. Install dependencies

```bash
pip install playwright requests beautifulsoup4
playwright install chromium
```

---

### 2. Collect businesses

**Option A — itis.siol.net (recommended, no Google needed)**

```bash
# Restaurants
python slovenian_scraper.py --source itis --category Gostilne-in-restavracije --pages 5

# Hairdressers in Ljubljana
python slovenian_scraper.py --source itis --category Frizerska-dejavnost --city Ljubljana --pages 3

# All businesses in Maribor (any category)
python slovenian_scraper.py --source itis --city Maribor --pages 10
```

Useful categories (paste exactly):
| Slovenian slug | English |
|---|---|
| `Gostilne-in-restavracije` | Restaurants |
| `Bar` | Bars |
| `Hoteli` | Hotels |
| `Frizerska-dejavnost` | Hairdressers |
| `Kozmeticna-dejavnost` | Beauty salons |
| `Avtoservis` | Car repair |
| `Gradbeništvo` | Construction |
| `Nepremicnine` | Real estate |
| `Zobozdravstvo` | Dentists |
| `Fitnes-in-skupinske-vadbe` | Gyms |
| `Trgovina` | Retail |
| `Zdravstvo` | Healthcare |
| `Racunovodstvo-in-knjigovodstvo` | Accountants |

**Option B — Google Maps (headless browser)**

```bash
python maps_scraper.py --query "restavracije" --location "Ljubljana, Slovenija" --max 50
# Remove --headless to watch the browser (easier to debug)
```

**Option C — bizi.si**

```bash
python slovenian_scraper.py --source bizi --query "restavracija" --pages 3
```

All scrapers append to `results.json` — you can run them multiple times to build up your list.

---

### 3. Audit websites

```bash
python audit_websites.py
```

This visits every website found and checks for:
- 🚫 No website at all
- 🔓 No HTTPS / SSL certificate
- 🆓 Free subdomain (wixsite.com, godaddysites.com, etc.)
- 🏗️ Website builder platform (Wix, GoDaddy, Squarespace, Weebly, Jimdo…)
- 📱 Not mobile-friendly (no viewport meta tag)
- ⏳ Outdated HTML / old jQuery
- 🐢 Slow server response (>3s)
- 🔍 Missing SEO meta description
- 📞 Phone number not listed on website

---

### 4. Open the dashboard

```bash
python build_dashboard.py
# Then open dashboard.html in your browser
```

The dashboard lets you:
- **Search** by name, city, website, phone
- **Filter** by specific issue (e.g. show only Wix sites)
- **Filter** by source (itis / bizi / Google Maps)
- **Sort** by number of issues (best leads first)
- **Hover** any card to see the sales pitch for that business
- **Export to CSV** for your CRM

---

## Sales workflow tip

1. Filter by `🚫 Brez spletne strani` (no website) — easiest wins
2. Filter by `🆓 Brezplačna domena` — businesses ready to upgrade
3. Filter by `🏗️ Wix` or `🏗️ GoDaddy` — use the auto-generated pitch
4. Export CSV → import into your CRM or cold email tool

---

## Files

| File | Purpose |
|---|---|
| `slovenian_scraper.py` | Scrapes itis.siol.net and bizi.si |
| `maps_scraper.py` | Scrapes Google Maps (needs Playwright) |
| `audit_websites.py` | Fetches and audits each website |
| `build_dashboard.py` | Generates dashboard.html from results.json |
| `results.json` | All collected + audited data (auto-created) |
| `dashboard.html` | Your sales dashboard (open in browser) |

---

## Notes

- `slovenian_scraper.py` uses only `requests` + `BeautifulSoup` — no browser needed, fast
- `maps_scraper.py` uses Playwright (headless Chrome) — slower, needs install
- Run scrapers multiple times with different categories to build a big list
- The audit adds ~0.5s delay per site to avoid overloading servers
- Results persist across runs — add more businesses without losing audit data
