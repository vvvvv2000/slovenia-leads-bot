"""
build_dashboard.py — Injects results.json into dashboard_template.html → dashboard.html.

Dashboard login password: leads2024
To change it:
    python -c "import hashlib; print(hashlib.sha256(b'YOURPASSWORD').hexdigest())"
    Then update PASSWORD_HASH below.

Usage:
    python build_dashboard.py
"""

import json
from pathlib import Path

RESULTS_FILE  = "results.json"
TEMPLATE_FILE = "dashboard_template.html"
OUTPUT_HTML   = "dashboard.html"

# SHA-256 of "leads2024"
PASSWORD_HASH = "b45438de6be52d4843917d64eae5fcfbe819b278e667b2efd993b0a29c118158"

ISSUE_META = {
    "no_website":           {"label": "🚫 No website",           "color": "#c0392b", "severity": 5},
    "no_ssl":               {"label": "🔓 No HTTPS",              "color": "#e67e22", "severity": 3},
    "free_domain":          {"label": "🆓 Free/subdomain URL",    "color": "#d35400", "severity": 4},
    "platform_wix":         {"label": "🏗️ Built on Wix",         "color": "#8e44ad", "severity": 3},
    "platform_godaddy":     {"label": "🏗️ Built on GoDaddy",     "color": "#8e44ad", "severity": 3},
    "platform_squarespace": {"label": "🏗️ Built on Squarespace", "color": "#8e44ad", "severity": 2},
    "platform_weebly":      {"label": "🏗️ Built on Weebly",      "color": "#8e44ad", "severity": 3},
    "platform_jimdo":       {"label": "🏗️ Built on Jimdo",       "color": "#8e44ad", "severity": 3},
    "platform_wordpress":   {"label": "🏗️ WordPress.com",        "color": "#8e44ad", "severity": 2},
    "no_mobile":            {"label": "📱 Not mobile-friendly",   "color": "#16a085", "severity": 3},
    "outdated_html":        {"label": "⏳ Outdated HTML",         "color": "#7f8c8d", "severity": 2},
    "old_jquery":           {"label": "⚙️ Old jQuery",           "color": "#7f8c8d", "severity": 2},
    "slow_response":        {"label": "🐢 Slow server",           "color": "#2980b9", "severity": 2},
    "no_favicon":           {"label": "🖼️ No favicon",           "color": "#bdc3c7", "severity": 1},
    "meta_missing":         {"label": "🔍 No SEO meta",           "color": "#95a5a6", "severity": 2},
    "phone_not_on_site":    {"label": "📞 Phone missing",         "color": "#2c3e50", "severity": 2},
}

SALES_PITCHES = {
    "no_website":           "Podjetje nima spletne strani — vsak dan izgublja stranke, ki iščejo po Googlu.",
    "no_ssl":               "Stran deluje brez HTTPS — brskalniki opozarjajo 'Ni varno'. Google jo kaznuje v iskalniku.",
    "free_domain":          "Spletni naslov je brezplačna poddomena (npr. podjetje.wixsite.com) — neprofesionalno in znižuje zaupanje.",
    "platform_wix":         "Stran je na Wixu — omejena SEO, počasno nalaganje, ni lastniških pravic kode.",
    "platform_godaddy":     "GoDaddy Website Builder: generični predlogi, slaba SEO, brez diferenciacije.",
    "platform_squarespace": "Squarespace: lepo videti, a omejeno SEO in ni prilagodljivosti za rast.",
    "platform_weebly":      "Weebly: osnovno orodje brez resnih SEO možnosti.",
    "platform_jimdo":       "Jimdo brezplačni plan prikazuje Jimdo oglaševanje in ima slabo SEO.",
    "platform_wordpress":   "WordPress.com brezplačni plan prikazuje oglase tretjih strani.",
    "no_mobile":            "Stran ni prilagojena za mobilne naprave — 60%+ prometa prihaja iz telefonov.",
    "outdated_html":        "Zastarela HTML koda — signal za zanemarjeno stran, ki jo Google slabše uvršča.",
    "old_jquery":           "Stara verzija jQuery z varnostnimi ranljivostmi.",
    "slow_response":        "Stran se nalaga počasi (>3s) — Google to upošteva pri rangiranju.",
    "no_favicon":           "Ni favicon ikone — videti kot nedokončana stran.",
    "meta_missing":         "Ni meta opisa — Google ga generira naključno, kar zmanjšuje CTR v iskalniku.",
    "phone_not_on_site":    "Telefonska številka ni navedena na spletni strani — težje vzpostaviti stik.",
}


def main():
    # Load template
    tpl_path = Path(TEMPLATE_FILE)
    if not tpl_path.exists():
        print(f"Template '{TEMPLATE_FILE}' not found. Make sure it's in the same folder.")
        return

    template = tpl_path.read_text(encoding="utf-8")

    # Load data
    results_path = Path(RESULTS_FILE)
    if results_path.exists():
        with open(results_path, encoding="utf-8") as f:
            businesses = json.load(f)
        print(f"Loaded {len(businesses)} businesses from {RESULTS_FILE}")
    else:
        print(f"No {RESULTS_FILE} found — building empty dashboard (run scrapers first).")
        businesses = []

    # Substitute placeholders
    html = template
    html = html.replace("%%DATA%%",       json.dumps(businesses,  ensure_ascii=False))
    html = html.replace("%%ISSUE_META%%", json.dumps(ISSUE_META,  ensure_ascii=False))
    html = html.replace("%%PITCHES%%",    json.dumps(SALES_PITCHES, ensure_ascii=False))
    html = html.replace("%%PW_HASH%%",    PASSWORD_HASH)

    # Write output
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    audited = sum(1 for b in businesses if b.get("audit"))
    print(f"Dashboard written to {OUTPUT_HTML}")
    print(f"  {len(businesses)} businesses | {audited} audited")
    print(f"  Login password: leads2024")


if __name__ == "__main__":
    main()
