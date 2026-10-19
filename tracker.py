import os
import time
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COURSES = [
    "Advanced (ICITSS) MCS Course",
    "AICITSS - Advanced Information Technology"
]

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials not found. Skipping Telegram send.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram status: {response.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def count_open_seats(page):
    js_code = """() => {
        const rows = document.querySelectorAll("tr");
        let seatColIdx = -1;
        let totalSeats = 0;

        for (let r = 0; r < rows.length; r++) {
            const cells = rows[r].children;
            if (seatColIdx === -1) {
                for (let c = 0; c < cells.length; c++) {
                    const txt = cells[c].innerText.trim().toLowerCase();
                    if (txt.includes("available seats") || (txt.includes("available") && txt.includes("seat"))) {
                        seatColIdx = c;
                        break;
                    }
                }
            } else {
                if (cells.length > seatColIdx) {
                    const val = parseInt(cells[seatColIdx].innerText.trim(), 10);
                    if (!isNaN(val) && val > 0) {
                        totalSeats += val;
                    }
                }
            }
        }
        return totalSeats;
    }"""
    return page.evaluate(js_code)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        print("Navigating to ICAI portal...")
        page.goto("https://www.icaionlineregistration.org/launchbatchdetail.aspx", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        print("Selecting Region: Central...")
        page.evaluate("""() => {
            const selects = Array.from(document.querySelectorAll('select'));
            const region = selects.find(s => (s.id + s.name).toLowerCase().includes('region'));
            if (!region) return;
            for (let i = 0; i < region.options.length; i++) {
                if (region.options[i].text.toLowerCase().includes('central')) {
                    region.selectedIndex = i;
                    if (typeof region.onchange === 'function') region.onchange();
                    else if (typeof window.__doPostBack === 'function') window.__doPostBack(region.name, '');
                    break;
                }
            }
        }""")
        page.wait_for_timeout(4000)

        print("Selecting POU: Indore...")
        page.evaluate("""() => {
            const selects = Array.from(document.querySelectorAll('select'));
            const pou = selects.find(s => (s.id + s.name).toLowerCase().includes('pou'));
            if (!pou) return;
            for (let i = 0; i < pou.options.length; i++) {
                if (pou.options[i].text.toLowerCase().includes('indore')) {
                    pou.selectedIndex = i;
                    if (typeof pou.onchange === 'function') pou.onchange();
                    else if (typeof window.__doPostBack === 'function') window.__doPostBack(pou.name, '');
                    break;
                }
            }
        }""")
        page.wait_for_timeout(4000)

        results = {}
        has_open_seats = False

        js_select_course = """(courseTarget) => {
            const selects = Array.from(document.querySelectorAll('select'));
            const cSelect = selects.find(s => (s.id + s.name).toLowerCase().includes('course'));
            if (!cSelect) return;
            for (let i = 0; i < cSelect.options.length; i++) {
                if (cSelect.options[i].text.toLowerCase().includes(courseTarget.toLowerCase().slice(0, 15))) {
                    cSelect.selectedIndex = i;
                    break;
                }
            }
        }"""

        js_click_get_list = """() => {
            const btn = Array.from(document.querySelectorAll('input, button')).find(el => (el.value || el.innerText || '').toLowerCase().includes('get list'));
            if (btn) btn.click();
        }"""

        for course in COURSES:
            print(f"Checking course: {course}...")
            page.evaluate(js_select_course, course)
            page.wait_for_timeout(1000)

            page.evaluate(js_click_get_list)
            page.wait_for_timeout(4000)

            seats = count_open_seats(page)
            results[course] = seats
            print(f"[{course}] Available seats: {seats}")

            if seats > 0:
                has_open_seats = True

        browser.close()

        # Build message for every check
        if has_open_seats:
            msg = "🚨 ICAI INDORE BATCH ALERT! SEATS OPEN! 🚨\n\n"
        else:
            msg = "📊 ICAI Indore Batch Status Update:\n\n"

        for course, seats in results.items():
            short_name = "MCS" if "MCS" in course else "Adv ITT"
            msg += f"• {short_name}: {seats} seats available\n"

        msg += "\n🔗 Portal: https://www.icaionlineregistration.org/launchbatchdetail.aspx"

        send_telegram(msg)
        print("Telegram status update sent successfully.")

if __name__ == "__main__":
    run()
