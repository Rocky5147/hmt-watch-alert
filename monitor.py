
import os
import json
import re
import requests

from pathlib import Path
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WATCHES_FILE = Path("watches.json")
STATE_FILE = Path("state.json")


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=20
    )

    response.raise_for_status()

    if not response.json().get("ok"):
        raise RuntimeError("Telegram notification failed")


def load_watches():
    with WATCHES_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    watches = data.get("watches", [])

    if not watches:
        raise RuntimeError("No watches configured.")

    ids = [watch["id"] for watch in watches]

    if len(ids) != len(set(ids)):
        raise RuntimeError("Every watch must have a unique ID.")

    for watch in watches:
        if not all(key in watch for key in ("id", "name", "url")):
            raise RuntimeError("A watch is missing required information.")

    return watches


def load_state():
    if not STATE_FILE.exists():
        return {"watches": {}}

    with STATE_FILE.open("r", encoding="utf-8") as file:
        state = json.load(file)

    if "watches" not in state:
        raise RuntimeError("Invalid state.json format.")

    return state


def save_state(state):
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


def check_stock(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True).lower()

    # Check the main product section.
    product_section = page_text.split("description", 1)[0]

    unavailable_patterns = [
        r"\bout\s+of\s+stock\b",
        r"\bsold\s+out\b",
        r"\bcurrently\s+unavailable\b",
        r"\bnotify\s+me\b"
    ]

    for pattern in unavailable_patterns:
        if re.search(pattern, product_section):
            return "OUT_OF_STOCK"

    if "add to cart" in product_section:
        return "IN_STOCK"

    raise RuntimeError(
        "Could not identify stock status on HMT website."
    )


def monitor_watch(watch, state):
    watch_id = watch["id"]
    name = watch["name"]
    url = watch["url"]

    if not url.startswith("https://"):
        raise ValueError(f"Invalid product URL for {name}")

    print(f"\nChecking {name}...")

    current = check_stock(url)
    previous = state["watches"].get(watch_id)

    print(f"Previous status: {previous}")
    print(f"Current status: {current}")

    if previous is None:
        send_telegram(
            f"✅ HMT STOCK MONITORING STARTED\n\n"
            f"Watch: {name}\n"
            f"Current status: {current.replace('_', ' ')}\n\n"
            f"Product link:\n{url}\n\n"
            f"I will notify you when availability changes."
        )

    elif previous == "OUT_OF_STOCK" and current == "IN_STOCK":
        send_telegram(
            f"🚨🚨 HMT WATCH BACK IN STOCK! 🚨🚨\n\n"
            f"Watch: {name}\n\n"
            f"Status: AVAILABLE!\n\n"
            f"Purchase now:\n{url}"
        )

    elif previous == "IN_STOCK" and current == "OUT_OF_STOCK":
        send_telegram(
            f"⚠️ HMT STOCK UPDATE\n\n"
            f"{name} is now OUT OF STOCK again."
        )

    state["watches"][watch_id] = current

    print(f"Completed: {name}")


def main():
    watches = load_watches()
    state = load_state()
    errors = []

    print(f"Monitoring {len(watches)} HMT watches.")

    for watch in watches:
        try:
            monitor_watch(watch, state)

        except Exception as error:
            print(f"ERROR checking {watch['name']}: {error}")
            errors.append(watch["name"])

    save_state(state)

    if errors:
        print(
            "Some watches could not be checked: "
            + ", ".join(errors)
        )

    print("\nMonitoring cycle completed.")


if __name__ == "__main__":
    main()
