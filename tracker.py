import os
import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COURSES = [
    "Advanced (ICITSS) MCS Course",
    "AICITSS - Advanced Information Technology"
]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def count_open_seats(page):
    """
    Parses table rows and extracts numeric values from the 'Available Seats' column.
    """
    return page.evaluate("""() => {
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
    }""")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.icaionlineregistration.org/launchbatchdetail.aspx", timeout=60000)

        # 1. Select Region -> Central
        page.select_option("select[id*='Region'], select[name*='Region']", label="Central")
        page.wait_for_timeout(3000)

        # 2. Select POU -> Indore
        page.select_option("select[id*='Pou'], select[name*='Pou'], select[id*='POU']", label="Indore")
        page.wait_for_timeout(3000)

        alerts = []

        # 3. Check both MCS and Adv ITT
        for course in COURSES:
            page.select_option("select[id*='Course'], select[name*='Course']", label=course)
            page.wait_for_timeout(2000)

            # Click Get List if present
            get_list_btn = page.query_selector("input[value*='Get List'], button[value*='Get List']")
            if get_list_btn:
                get_list_btn.click()
                page.wait_for_timeout(3000)

            seats = count_open_seats(page)
            print(f"[{course}] Available seats: {seats}")

            if seats > 0:
                alerts.append(f"• {course}: {seats} seat(s) available")

        browser.close()

        if alerts:
            message = "🚨 ICAI INDORE BATCH ALERT! 🚨\n\n"
            message += "\n".join(alerts)
            message += "\n\nRegister immediately: https://www.icaionlineregistration.org/launchbatchdetail.aspx"
            send_telegram(message)
            print("Alert notification sent to Telegram.")
        else:
            print("No seats open at this time.")

if __name__ == "__main__":
    run()
