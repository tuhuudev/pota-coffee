"""Build the static site into dist/ from data/shop.json (the single source of truth).

Outputs: index.html (with JSON-LD), index.md (Markdown for agents),
llms.txt, robots.txt, sitemap.xml.

Usage:  SITE_URL=https://pota-coffee.tuhuu-dev.workers.dev/ python3 build.py
"""
import html
import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
SITE_URL = os.environ.get("SITE_URL", "https://pota-coffee.tuhuu-dev.workers.dev/").rstrip("/") + "/"

D = json.loads((ROOT / "data" / "shop.json").read_text(encoding="utf-8"))
SHOP, CATS, MENU, REVIEWS = D["shop"], D["categories"], D["menu"], D["reviews"]
SIZES = D["sizes"]


def vnd(n):
    return f"{n:,}".replace(",", ".") + " đ"


def e(s):
    return html.escape(str(s), quote=True)


# ---------- JSON-LD ----------
prices = [m["price"] for m in MENU]
jsonld = {
    "@context": "https://schema.org",
    "@type": "CafeOrCoffeeShop",
    "name": SHOP["name"],
    "url": SITE_URL,
    "servesCuisine": "Cà phê Việt Nam",
    "priceRange": f"{min(prices):,}–{max(prices):,} VND".replace(",", "."),
    "openingHours": SHOP["hours"],
    "telephone": SHOP["phone"],
    "address": {"@type": "PostalAddress", "streetAddress": SHOP["address"],
                "addressLocality": SHOP["city"], "addressRegion": SHOP["region"],
                "addressCountry": "VN"},
    "hasMenu": {"@type": "Menu", "hasMenuSection": [
        {"@type": "MenuSection", "name": label, "hasMenuItem": [
            {"@type": "MenuItem", "name": m["name"], "description": m["desc"],
             "offers": {"@type": "Offer", "price": m["price"], "priceCurrency": "VND",
                        "availability": "https://schema.org/InStock"}}
            for m in MENU if m["cat"] == key]}
        for key, label in CATS.items()]},
}
jsonld_str = json.dumps(jsonld, ensure_ascii=False, indent=2)

# ---------- Markdown for agents ----------
md = [f"# {SHOP['name']}", "",
      f"Quán cà phê mang đi tại {SHOP['city']}. Giờ mở cửa: {SHOP['hours_text']}. Điện thoại: {SHOP['phone']}.", ""]
for key, label in CATS.items():
    md.append(f"## {label}")
    md += [f"- {m['name']}: {vnd(m['price'])} — {m['desc']}" for m in MENU if m["cat"] == key]
    md.append("")
extra = [s for s in SIZES if s["extra"]]
if extra:
    md.append("Size: " + ", ".join(f"{s['label']} +{vnd(s['extra'])}" for s in extra) + ".")
md.append(f"Đặt món: {SITE_URL}#dat-mon (form là WebMCP tool `dat_mon`).")
markdown_str = "\n".join(md) + "\n"

# ---------- HTML pieces ----------
ART = {  # small inline illustrations per category (no photos yet)
    "ca-phe": '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M14 24h30v14a13 13 0 0 1-13 13h-4A13 13 0 0 1 14 38z" fill="currentColor" opacity=".9"/><path d="M44 28h4a6 6 0 0 1 0 12h-5" fill="none" stroke="currentColor" stroke-width="4"/><path d="M22 10c0 4 4 4 4 8M30 8c0 4 4 4 4 8" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" opacity=".55"/><rect x="10" y="53" width="40" height="4" rx="2" fill="currentColor" opacity=".5"/></svg>',
    "tra": '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M18 18h28l-4 38H22z" fill="currentColor" opacity=".9"/><path d="M36 18l6-12" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><circle cx="27" cy="34" r="3.5" fill="#fff" opacity=".7"/><circle cx="36" cy="42" r="3" fill="#fff" opacity=".6"/><path d="M19 26h26" stroke="#fff" stroke-width="2" opacity=".5"/></svg>',
    "khac": '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M17 22h30l-3 34H20z" fill="currentColor" opacity=".9"/><path d="M14 16h36v6H14z" fill="currentColor"/><path d="M24 16c0-6 16-6 16 0" fill="currentColor" opacity=".6"/><path d="M21 34c7 4 15-4 22 0" stroke="#fff" stroke-width="3" fill="none" opacity=".55"/></svg>',
}
SPRITE = '<svg width="0" height="0" style="position:absolute" aria-hidden="true">' + "".join(
    f'<symbol id="a-{k}" viewBox="0 0 64 64">' + re.sub(r'^<svg[^>]*>|</svg>$', '', v) + '</symbol>' for k, v in ART.items()) + '</svg>'
ART = {k: f'<svg viewBox="0 0 64 64" aria-hidden="true"><use href="#a-{k}"/></svg>' for k in ART}
cards, dialogs = [], []
for m in MENU:
    cards.append(f'''
      <li class="card" data-cat="{m['cat']}" style="view-transition-name: item-{m['id']}">
        <div class="art art-{m['cat']}">{ART[m['cat']]}</div>
        <div class="card-body">
          <span class="chip">{e(m['tag'])}</span>
          <h3>{e(m['name'])}</h3>
          <p class="desc">{e(m['desc'])}</p>
          <div class="card-foot">
            <p class="price">{vnd(m['price'])}</p>
            <button type="button" class="pick" commandfor="dlg-{m['id']}" command="show-modal">Chọn<span class="sr"> {e(m['name'])}</span></button>
          </div>
        </div>
      </li>''')
    size_radios = "".join(
        f'<label class="seg"><input type="radio" name="size" value="{s["id"]}"{" checked" if i == 0 else ""}>'
        f'<span><b>{e(s["id"])}</b><small>{"+" + vnd(s["extra"]) if s["extra"] else "giá gốc"}</small></span></label>'
        for i, s in enumerate(SIZES))
    dialogs.append(f'''
  <dialog id="dlg-{m['id']}" class="sheet" aria-labelledby="dlg-{m['id']}-t">
    <form method="dialog" class="item-form" data-item="{m['id']}">
      <div class="sheet-head">
        <div class="art art-{m['cat']}">{ART[m['cat']]}</div>
        <div>
          <h2 id="dlg-{m['id']}-t">{e(m['name'])}</h2>
          <p class="desc">{e(m['desc'])}</p>
        </div>
        <button type="button" class="x" commandfor="dlg-{m['id']}" command="close" aria-label="Đóng">&times;</button>
      </div>
      <fieldset class="sizes"><legend>Size</legend>{size_radios}</fieldset>
      <div class="qty-row">
        <span class="lbl" id="q-{m['id']}">Số lượng</span>
        <div class="stepper">
          <button type="button" data-step="-1" aria-label="Bớt 1 ly">&minus;</button>
          <input type="number" name="qty" value="1" min="1" max="20" inputmode="numeric" aria-labelledby="q-{m['id']}">
          <button type="button" data-step="1" aria-label="Thêm 1 ly">+</button>
        </div>
      </div>
      <label class="note">Ghi chú <input type="text" name="note" placeholder="Ít đá, ít ngọt…"></label>
      <button type="submit" class="btn primary block">Thêm vào giỏ · <span data-line-total>{vnd(m['price'])}</span></button>
    </form>
  </dialog>''')

options = "\n".join(
    f'<option value="{m["id"]}"><span class="opt-name">{e(m["name"])}</span><span class="sep"> · </span>'
    f'<span class="opt-price">{vnd(m["price"])}</span></option>' for m in MENU)
size_opts = "\n".join(
    f'<option value="{s["id"]}"><span class="opt-name">{e(s["label"])}</span><span class="sep"> · </span>'
    f'<span class="opt-price">{"+" + vnd(s["extra"]) if s["extra"] else "giá gốc"}</span></option>' for s in SIZES)
reviews_html = "\n".join(f"<li>{e(r)}</li>" for r in REVIEWS)
client_data = json.dumps({"menu": MENU, "sizes": {s["id"]: s["extra"] for s in SIZES},
                          "reviews": REVIEWS, "open": SHOP.get("open", "06:00"),
                          "close": SHOP.get("close", "21:00")}, ensure_ascii=False)

tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
page = (tpl.replace("%%JSONLD%%", jsonld_str.replace("</", "<\\/"))
           .replace("%%CARDS%%", "".join(cards))
           .replace("%%DIALOGS%%", "".join(dialogs))
           .replace("%%OPTIONS%%", options)
           .replace("%%SIZE_OPTIONS%%", size_opts)
           .replace("%%REVIEWS%%", reviews_html)
           .replace("%%CLIENT_DATA%%", client_data.replace("</", "<\\/"))
           .replace("%%MARKDOWN%%", e(markdown_str))
           .replace("%%JSONLD_PRETTY%%", e(jsonld_str))
           .replace("%%HOURS%%", e(SHOP["hours_text"]))
           .replace("%%CITY%%", e(SHOP["city"]))
           .replace("tel:%%PHONE%%", "tel:" + "".join(c for c in SHOP["phone"] if c.isdigit() or c == "+"))
           .replace("%%PHONE%%", e(SHOP["phone"]))
           .replace("%%ADDRESS%%", e(SHOP["address"]))
           .replace("%%SITE_URL%%", e(SITE_URL))
           .replace("%%SPRITE%%", SPRITE)
           .replace("%%TAGLINE%%", e(SHOP.get("tagline", ""))))
sha = os.environ.get("WORKERS_CI_COMMIT_SHA") or os.environ.get("GITHUB_SHA")
if not sha:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except OSError:
        sha = ""
page = page.replace("</html>", f"<!-- build: {(sha or 'local')[:7]} -->\n</html>")
assert "%%" not in page, "placeholder chưa được thay"

# ---------- write dist ----------
shutil.rmtree(DIST, ignore_errors=True)
DIST.mkdir()
(DIST / "index.html").write_text(page, encoding="utf-8")
(DIST / "index.md").write_text(markdown_str, encoding="utf-8")
(DIST / "llms.txt").write_text(
    f"# {SHOP['name']}\n\n> Quán cà phê mang đi tại {SHOP['city']}.\n\n"
    f"- [Menu và giá (Markdown)]({SITE_URL}index.md)\n- [Trang chính]({SITE_URL})\n", encoding="utf-8")
(DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")
(DIST / "sitemap.xml").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    f"  <url><loc>{SITE_URL}</loc><lastmod>{date.today().isoformat()}</lastmod></url>\n</urlset>\n", encoding="utf-8")
(DIST / ".nojekyll").write_text("")
print(f"built {len(page):,} bytes -> dist/ ({SITE_URL})")
