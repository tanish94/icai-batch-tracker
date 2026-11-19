import json
import os
import re
import sys
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.icaionlineregistration.org/launchbatchdetail.aspx"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FORCE = os.getenv("FORCE_NOTIFY", "").lower() == "true"
STATE_FILE = "state.json"

REGION = "central"
POU = "indore"
COURSES = [
    ("MCS", "Advanced (ICITSS) MCS Course"),
    ("Adv ITT", "AICITSS - Advanced Information Technology"),
    # ("MCS Weekend", "Advanced (ICITSS) MCS Course - Weekend"),  # uncomment if you want this too
]


# ---------- Telegram ----------
def tg_text(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing.")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text[:4000], "disable_web_page_preview": True},
        timeout=30,
    )
    print("Telegram text:", r.status_code, r.text[:200])


def tg_photo(path, caption):
    if not BOT_TOKEN or not CHAT_ID:
        return
    with open(path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            files={"photo": f},
            data={"chat_id": CHAT_ID, "caption": caption[:1000]},
            timeout=60,
        )
    print("Telegram photo:", r.status_code)


# ---------- Page helpers ----------
def choose(page, keyword, wanted):
    """Pick the <select> whose id/name contains `keyword`, choose the option containing `wanted`."""
    sel_id = page.evaluate(
        """(kw) => {
            const s = Array.from(document.querySelectorAll('select'))
                .find(s => (s.id + ' ' + s.name).toLowerCase().includes(kw));
            return s ? s.id : null;
        }""",
        keyword,
    )
    if not sel_id:
        raise RuntimeError(f"No dropdown found for '{keyword}'")

    # Wait until the option exists (POU only fills after Region postback)
    page.wait_for_function(
        """([id, w]) => {
            const s = document.getElementById(id);
            return s && Array.from(s.options).some(o => o.text.toLowerCase().includes(w));
        }""",
        arg=[sel_id, wanted.lower()],
        timeout=30000,
    )
    label = page.evaluate(
        """([id, w]) => Array.from(document.getElementById(id).options)
            .find(o => o.text.toLowerCase().includes(w)).text""",
        [sel_id, wanted.lower()],
    )
    page.select_option(f'[id="{sel_id}"]', label=label)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)  # let the ASP.NET postback finish
    print(f"Selected {keyword}: {label}")


def get_tables(page):
    return page.evaluate(
        r"""() => {
            const out = [];
            document.querySelectorAll('table').forEach(t => {
                if (t.querySelector('table')) return;   // skip layout tables
                const rows = Array.from(t.querySelectorAll('tr')).map(tr =>
                    Array.from(tr.querySelectorAll('th,td')).map(c => c.innerText.trim().replace(/\s+/g, ' ')));
                const good = rows.filter(r => r.length >= 3);
                if (good.length >= 2) out.push(good);
            });
            return out;
        }"""
    )


def parse_batches(table):
    header = [h.lower() for h in table[0]]
    seat_idx = next(
        (i for i, h in enumerate(header) if any(k in h for k in ("seat", "vacan", "availab"))),
        None,
    )
    batches = []
    for row in table[1:]:
        seats = None
        if seat_idx is not None and seat_idx < len(row):
            m = re.search(r"\d+", row[seat_idx])
            if m:
                seats = int(m.group())
        key = " | ".join(c for i, c in enumerate(row) if i != seat_idx)
        batches.append({"key": key, "seats": seats, "row": row})
    return header, seat_idx, batches


def check_course(browser, label, course):
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 1000},
    )
    page = context.new_page()
    tag = label.replace(" ", "_").lower()
    try:
        for attempt in (1, 2):
            try:
                page.goto(URL, timeout=60000, wait_until="domcontentloaded")
                break
            except Exception as e:
                print(f"goto attempt {attempt} failed: {e}")
                if attempt == 2:
                    raise
        page.wait_for_load_state("networkidle")

        choose(page, "region", REGION)
        choose(page, "pou", POU)
        choose(page, "course", course)

        btn = page.locator("input[value*='Get List' i], button:has-text('Get List')").first
        btn.click()
        page.wait_for_load_state("networkidle")

        # wait for a results table (or give it a fixed grace period)
        try:
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('table')).some(t =>
                    !t.querySelector('table') && t.querySelectorAll('tr').length >= 2 &&
                    t.querySelectorAll('tr')[1].querySelectorAll('td').length >= 3)""",
                timeout=20000,
            )
        except Exception:
            print("No results table appeared within 20s")

        page.wait_for_timeout(1500)
        page.screenshot(path=f"debug_{tag}.png", full_page=True)
        with open(f"debug_{tag}.html", "w", encoding="utf-8") as f:
            f.write(page.content())

        tables = get_tables(page)
        if not tables:
            body = page.inner_text("body")
            print("No table found. Page text:\n", body[:1500])
            return {"label": label, "batches": [], "header": [], "note": "no table"}

        table = max(tables, key=len)
        header, seat_idx, batches = parse_batches(table)
        print(f"[{label}] header={header} seat_col={seat_idx} rows={len(batches)}")
        for b in batches:
            print("   ", b["row"])
        return {"label": label, "batches": batches, "header": header, "seat_idx": seat_idx}
    except Exception as e:
        try:
            page.screenshot(path=f"debug_{tag}.png", full_page=True)
            tg_photo(f"debug_{tag}.png", f"⚠️ Checker failed for {label}: {e}")
        except Exception:
            tg_text(f"⚠️ Checker failed for {label}: {e}")
        raise
    finally:
        context.close()


# ---------- Main ----------
def main():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            state = {}

    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for label, course in COURSES:
            try:
                res = check_course(browser, label, course)
            except Exception as e:
                print(f"[{label}] FAILED: {e}")
                failures += 1
                continue

            prev = state.get(label)           # None on first ever run
            prev = prev if prev is not None else {}
            current = {b["key"]: b["seats"] for b in res["batches"]}
            alerts = []

            for b in res["batches"]:
                old = prev.get(b["key"], "NEW")
                is_new = old == "NEW"
                opened = (b["seats"] or 0) > 0 and (old in ("NEW", None, 0))
                if is_new or opened:
                    tag = "🆕 NEW BATCH" if is_new else "🟢 SEATS OPENED"
                    alerts.append(f"{tag}\n" + " | ".join(b["row"]))

            first_run = label not in state
            if FORCE or first_run:
                lines = [f"📋 {label} – Indore, current list ({len(current)} batches):"]
                lines += [" | ".join(b["row"]) for b in res["batches"]] or ["(no rows found)"]
                tg_text("\n".join(lines))
            elif alerts:
                tg_text(f"🔔 ICAI Indore – {label}\n\n" + "\n\n".join(alerts) + f"\n\n{URL}")
            else:
                print(f"[{label}] no change")

            state[label] = current

    json.dump(state, open(STATE_FILE, "w"), indent=2)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
