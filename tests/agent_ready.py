"""Agent-readiness checks. Run against the local build or the live site.

    python3 tests/agent_ready.py                 # test dist/ via a local server
    python3 tests/agent_ready.py --url https://tuhuudev.github.io/pota-coffee/

Hard checks (fail the build): crawler without JS sees menu + prices, JSON-LD
prices match data, every button / form control has an accessible name, a
role+name agent can place an order and open an item. Soft metrics (reported):
load time on a throttled phone, sizes, token estimate.
"""
import argparse, functools, gzip, http.server, json, os, re, statistics, sys, threading, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "shop.json").read_text(encoding="utf-8"))
ap = argparse.ArgumentParser(); ap.add_argument("--url"); ap.add_argument("--runs", type=int, default=5)
args = ap.parse_args()

if args.url:
    BASE = args.url.rstrip("/") + "/"
else:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Quiet, directory=str(ROOT / "dist"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    BASE = f"http://127.0.0.1:{srv.server_address[1]}/"

checks, metrics = [], {}
# Cloudflare blocks the default "Python-urllib" UA at the edge; real agents send their own UA.
AGENT_UA = "Claude-User/1.0 (agent-ready test; +https://github.com/tuhuudev/pota-coffee)"
def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})

def vnd(n): return f"{n:,}".replace(",", ".")

# ---------- 1. crawler without JS ----------
req = urllib.request.Request(BASE, headers={"User-Agent": "GPTBot/1.2 (agent-ready test)"})
raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw)))
missing = [m["name"] for m in DATA["menu"] if m["name"] not in text or vnd(m["price"]) not in text]
check("Crawler không chạy JS thấy đủ tên món và giá", not missing, ", ".join(missing))
ld = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', raw)
try:
    j = json.loads(ld.group(1))
    ld_prices = {i["name"]: i["offers"]["price"] for s in j["hasMenu"]["hasMenuSection"] for i in s["hasMenuItem"]}
    wrong = [m["name"] for m in DATA["menu"] if ld_prices.get(m["name"]) != m["price"]]
    check("JSON-LD hợp lệ và giá khớp dữ liệu", not wrong, ", ".join(wrong))
except Exception as ex:
    check("JSON-LD hợp lệ và giá khớp dữ liệu", False, str(ex))
try:
    md = urllib.request.urlopen(urllib.request.Request(BASE + "index.md", headers={"User-Agent": AGENT_UA}), timeout=30).read().decode("utf-8")
    check("Có bản Markdown index.md", all(m["name"] in md for m in DATA["menu"]))
    metrics["markdown_tokens_est"] = round(len(md) / 3.2)
except Exception as ex:
    check("Có bản Markdown index.md", False, str(ex))
try:
    r = urllib.request.urlopen(urllib.request.Request(BASE, headers={"Accept": "text/markdown", "User-Agent": AGENT_UA}), timeout=30)
    metrics["markdown_negotiation"] = r.headers.get("content-type", "").startswith("text/markdown")
except Exception:
    metrics["markdown_negotiation"] = False
metrics["html_kb"] = round(len(raw.encode()) / 1024, 1)
metrics["html_gz_kb"] = round(len(gzip.compress(raw.encode(), 9)) / 1024, 1)
metrics["html_tokens_est"] = round(len(raw) / 3.2)

# ---------- 2-4. browser ----------
exe = "/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") and not os.environ.get("CI") else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    errors = []; pg.on("pageerror", lambda ex: errors.append(str(ex)))
    pg.goto(BASE); pg.wait_for_timeout(800)
    check("Không có lỗi JavaScript", not errors, "; ".join(errors)[:200])

    snap = pg.locator("body").aria_snapshot()
    metrics["a11y_tree_tokens_est"] = round(len(snap) / 3.2)
    unnamed_btn = len(re.findall(r"- button(?! \")", snap))
    unnamed_ctl = len(re.findall(r"- (combobox|spinbutton|textbox)(?! \")", snap))
    check("Mọi nút đều có tên truy cập", unnamed_btn == 0, f"{unnamed_btn} nút không tên")
    check("Mọi ô nhập đều có tên truy cập", unnamed_ctl == 0, f"{unnamed_ctl} ô không tên")
    check("Có landmark main + navigation", "- main" in snap and "- navigation" in snap)

    # agent task: order 2 x most expensive coffee, size with largest extra
    target = max((m for m in DATA["menu"] if m["cat"] == "ca-phe"), key=lambda m: m["price"])
    big = max(DATA["sizes"], key=lambda s: s["extra"])
    expected = (target["price"] + big["extra"]) * 2
    def choose(name, text):
        c = pg.get_by_role("combobox", name=name)
        val = c.evaluate("(e, t) => [...e.options].find(o => o.textContent.includes(t)).value", text)
        c.select_option(val)
    try:
        choose("Món", target["name"]); choose("Size", big["label"])
        pg.get_by_role("spinbutton", name="Số lượng").fill("2")
        pg.get_by_role("button", name="Thêm vào giỏ").first.click()
        pg.wait_for_timeout(200)
        total = pg.locator("#cart-total").inner_text()
        check(f"Agent đặt 2 × {target['name']} ({big['label']})", vnd(expected) in total, f"giỏ = {total}, cần {vnd(expected)} đ")
    except Exception as ex:
        check(f"Agent đặt 2 × {target['name']} ({big['label']})", False, str(ex).splitlines()[0][:160])
    try:
        last = DATA["menu"][-1]["name"]
        pg.get_by_role("button", name=f"Xem chi tiết {last}").click(timeout=3000)
        check(f"Agent mở chi tiết {last}", pg.get_by_role("dialog", name=last).is_visible())
    except Exception as ex:
        check(f"Agent mở chi tiết {DATA['menu'][-1]['name']}", False, str(ex).splitlines()[0][:160])
    ctx.close()

    # throttled phone: CPU 4x + 1.6 Mbps / 150 ms
    times = []
    for _ in range(args.runs):
        ctx = b.new_context(viewport={"width": 390, "height": 844}); pg = ctx.new_page()
        if not args.url:  # sandbox/CI often can't reach Google Fonts
            ctx.route(re.compile(r"fonts\.(googleapis|gstatic)\.com"), lambda r: r.abort())
        cdp = ctx.new_cdp_session(pg); cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                 "downloadThroughput": 200000, "uploadThroughput": 93750})
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        pg.goto(BASE, wait_until="commit")
        pg.get_by_text(DATA["menu"][0]["name"]).first.wait_for(timeout=30000)
        times.append(pg.evaluate("performance.now()")); ctx.close()
    metrics["menu_visible_ms_median"] = round(statistics.median(times))
    b.close()

ok = all(c["ok"] for c in checks)
out = {"target": BASE, "ok": ok, "checks": checks, "metrics": metrics}
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [f"## Agent-ready: {'ĐẠT' if ok else 'CHƯA ĐẠT'}", f"Target: {BASE}", "", "| Kiểm tra | Kết quả | Chi tiết |", "|---|---|---|"]
lines += [f"| {c['check']} | {'✅' if c['ok'] else '❌'} | {c['detail']} |" for c in checks]
lines += ["", "| Chỉ số | Giá trị |", "|---|---|"] + [f"| {k} | {v} |" for k, v in metrics.items()]
report = "\n".join(lines)
print(report)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write(report + "\n")
sys.exit(0 if ok else 1)
