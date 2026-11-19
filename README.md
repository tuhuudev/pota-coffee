# Pota's Coffee

Website cho quán cà phê mang đi Pota's Coffee (Phan Thiết), làm theo hướng **AI-friendly & browser-native**: HTML tĩnh, đúng ngữ nghĩa, JS tối thiểu, có dữ liệu cho AI search và tool cho AI agent.

Site chính (Cloudflare Workers): https://pota-coffee.tuhuu-dev.workers.dev/

> Menu, giá, đánh giá, số điện thoại hiện là **dữ liệu mẫu**. Sửa trong `data/shop.json`.

## Cấu trúc

```
data/shop.json        Nguồn dữ liệu duy nhất (quán, menu, size, đánh giá)
src/template.html     Giao diện, CSS, JS
worker/index.js       Cloudflare Worker: trả Markdown khi Accept: text/markdown + ghi log bot vào D1
wrangler.toml         Cấu hình Worker + static assets dist/, D1 binding DB
build.py              Sinh dist/: index.html (+ JSON-LD), index.md, llms.txt, robots.txt, sitemap.xml
tests/agent_ready.py  Kiểm tra "agent-ready" + đo tốc độ trên điện thoại giả lập
.github/workflows/    Test → đẩy main sang nhánh production → Cloudflare deploy → test site thật
```

## Sửa menu

1. Sửa `data/shop.json` (tên, giá, mô tả, nhóm).
2. Commit lên `main`. GitHub Actions chạy test; đạt thì đẩy sang nhánh `production`, Cloudflare chỉ deploy nhánh này. Test fail thì site giữ bản cũ.
3. HTML, JSON-LD và Markdown luôn khớp nhau vì cùng sinh từ một file.

## Chạy local

```bash
pip install playwright && python -m playwright install chromium
python build.py
python -m http.server -d dist 8000          # xem tại http://localhost:8000
python tests/agent_ready.py                  # test bản build
python tests/agent_ready.py --url https://tuhuudev.github.io/pota-coffee/   # test site thật
```

## Test kiểm tra gì

Fail là chặn deploy:

- Bot không chạy JS (GPTBot, ClaudeBot, PerplexityBot) thấy đủ tên món và giá trong HTML
- JSON-LD hợp lệ, giá khớp `data/shop.json`
- Có `index.md` cho agent
- Không lỗi JavaScript
- Mọi nút và ô nhập có tên truy cập (accessibility tree sạch)
- Agent chỉ dùng role + tên (như Playwright MCP, Claude in Chrome) đặt được món và mở được chi tiết món

Chỉ báo cáo: thời gian hiện menu với CPU chậm 4x + mạng 1,6 Mbps, dung lượng HTML, ước tính token.
Kết quả xem ở tab **Actions → run → Summary**.

## Công nghệ đang dùng

| Tính năng | Dùng làm gì |
|---|---|
| Semantic HTML + ARIA | Agent đọc accessibility tree |
| JSON-LD `CafeOrCoffeeShop` + `Menu` | AI search lấy đúng giá, giờ mở cửa |
| `index.md`, `llms.txt` | Bản rút gọn cho agent |
| `<dialog>`, `popover`, Invoker Commands | Modal, tooltip không cần thư viện |
| CSS Anchor Positioning | Tooltip bám theo nút |
| `appearance: base-select` | Select tùy biến (enhancement) |
| View Transitions | Hiệu ứng lọc menu |
| WebMCP (`toolname`, `registerTool`) | Agent đặt món qua tool (Chrome 149+, origin trial) |
| Summarizer API | Tóm tắt đánh giá trên máy (có fallback) |

## Lộ trình cải thiện

- [ ] Thay dữ liệu mẫu bằng menu, giá, địa chỉ, số điện thoại thật
- [ ] Ảnh món (WebP/AVIF, `width`/`height`, `loading="lazy"`)
- [ ] Tên miền riêng + Google Search Console + liên kết từ Google Maps
- [ ] "Gửi đơn" gửi về bot Telegram của chủ quán
- [x] Cloudflare Worker + static assets: trả Markdown khi `Accept: text/markdown`, log bot AI vào D1 `pota-coffee-analytics`
- [ ] Đăng ký WebMCP origin trial, thêm token vào `<meta http-equiv="origin-trial">`
- [ ] Theo dõi hằng tuần: hỏi ChatGPT / Perplexity / Gemini "cà phê mang đi Phan Thiết" và ghi kết quả

## Quy trình deploy

`main` → GitHub Actions test → đạt thì đẩy sang `production` → Cloudflare Workers Builds deploy → test lại site thật (đợi đúng commit lên rồi mới test).

## Xem log bot AI (D1)

```sql
-- Bot nào ghé, bao nhiêu lần, 30 ngày gần nhất
SELECT bot, kind, COUNT(*) n, SUM(wants_markdown) md
FROM hits WHERE ts > datetime('now','-30 day') AND bot IS NOT NULL
GROUP BY bot, kind ORDER BY n DESC;
```

Chạy trong Cloudflare dashboard → D1 → pota-coffee-analytics → Console, hoặc nhờ Claude query qua connector.
