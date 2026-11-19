"""Build the static site into dist/ from data/shop.json (the single source of truth).

Outputs: index.html (with JSON-LD), index.md (Markdown for agents),
llms.txt, robots.txt, sitemap.xml.

Usage:  SITE_URL=https://pota-coffee.tuhuu-dev.workers.dev/ python3 build.py
"""
import html
import json
import os
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
cards, dialogs = [], []
for m in MENU:
    cards.append(f'''
      <li class="card" data-cat="{m['cat']}" style="view-transition-name: item-{m['id']}">
        <div class="card-top">
          <span class="chip">{e(m['tag'])}</span>
          <span class="cat">{e(CATS[m['cat']])}</span>
        </div>
        <h3>{e(m['name'])}</h3>
        <p class="price">{vnd(m['price'])}</p>
        <button type="button" class="btn ghost" commandfor="dlg-{m['id']}" command="show-modal"
                aria-label="Xem chi tiết {e(m['name'])}">Chi tiết</button>
      </li>''')
    dialogs.append(f'''
  <dialog id="dlg-{m['id']}" aria-labelledby="dlg-{m['id']}-t">
    <h2 id="dlg-{m['id']}-t">{e(m['name'])}</h2>
    <p>{e(m['desc'])}</p>
    <p class="price big">{vnd(m['price'])} <small>(size M)</small></p>
    <div class="row">
      <button type="button" class="btn" data-quick-add="{m['id']}" commandfor="dlg-{m['id']}" command="close">Thêm vào giỏ</button>
      <button type="button" class="btn ghost" commandfor="dlg-{m['id']}" command="close">Đóng</button>
    </div>
  </dialog>''')

options = "\n".join(
    f'<option value="{m["id"]}"><span class="opt-name">{e(m["name"])}</span><span class="sep"> · </span>'
    f'<span class="opt-price">{vnd(m["price"])}</span></option>' for m in MENU)
size_opts = "\n".join(
    f'<option value="{s["id"]}"><span class="opt-name">{e(s["label"])}</span><span class="sep"> · </span>'
    f'<span class="opt-price">{"+" + vnd(s["extra"]) if s["extra"] else "giá gốc"}</span></option>' for s in SIZES)
reviews_html = "\n".join(f"<li>{e(r)}</li>" for r in REVIEWS)
client_data = json.dumps({"menu": MENU, "sizes": {s["id"]: s["extra"] for s in SIZES},
                          "reviews": REVIEWS}, ensure_ascii=False)

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
           .replace("%%PHONE%%", e(SHOP["phone"]))
           .replace("%%ADDRESS%%", e(SHOP["address"]))
           .replace("%%SITE_URL%%", e(SITE_URL)))
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
