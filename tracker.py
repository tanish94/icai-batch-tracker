import os
import time
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COURSES = [
    ("MCS", "Advanced (ICITSS) MCS Course"),
    ("Adv ITT", "AICITSS - Advanced Information Technology")
]

def send_telegram_photo(photo_path, caption):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            res = requests.post(url, files=files, data=data, timeout=30)
            print(f"Telegram photo sent: {res.status_code}")
    except Exception as e:
        print(f"Error sending photo to Telegram: {e}")

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
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        print("Navigating to ICAI portal...")
        page.goto("https://www.icaionlineregistration.org/launchbatchdetail.aspx", timeout=60000, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 1. Select Region: Central
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
        # Wait for the postback to populate POU dropdown
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)

        # 2. Select POU: Indore
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
        # Wait for postback after POU change
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)

        # 3. For each course, select, trigger 'Get List', wait for results, and screenshot
        for label, course in COURSES:
            print(f"Selecting course: {course}...")
            page.evaluate("""(courseTarget) => {
                const selects = Array.from(document.querySelectorAll('select'));
                const cSelect = selects.find(s => (s.id + s.name).toLowerCase().includes('course'));
                if (!cSelect) return;
                for (let i = 0; i < cSelect.options.length; i++) {
                    if (cSelect.options[i].text.toLowerCase().includes(courseTarget.toLowerCase().slice(0, 15))) {
                        cSelect.selectedIndex = i;
                        if (typeof cSelect.onchange === 'function') cSelect.onchange();
                        break;
                    }
                }
            }""", course)
            page.wait_for_timeout(2000)

            print(f"Clicking Get List for {label}...")
            # Click Get List using native locator
            btn = page.locator("input[value*='Get List'], input[value*='get list'], button:has-text('Get List')").first
            if btn.count() > 0:
                btn.click()
            else:
                # Fallback JS trigger
                page.evaluate("""() => {
                    const b = Array.from(document.querySelectorAll('input, button')).find(el => (el.value || el.innerText || '').toLowerCase().includes('get list'));
                    if (b) b.click();
                }""")

            # Crucial: Wait for the network calls to settle and the table rows to populate
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            # Scroll slightly to center the table neatly in the screenshot
            page.evaluate("""() => {
                const table = document.querySelector('table[id*="grid"], table[id*="Grid"], table.table, table');
                if (table) table.scrollIntoView({behavior: 'instant', block: 'center'});
            }""")
            page.wait_for_timeout(1000)

            screenshot_file = f"{label.replace(' ', '_').lower()}.png"
            page.screenshot(path=screenshot_file, full_page=False)

            caption = f"📸 ICAI Indore Batch Status: {label}\n🔗 https://www.icaionlineregistration.org/launchbatchdetail.aspx"
            send_telegram_photo(screenshot_file, caption)
            page.wait_for_timeout(1000)
