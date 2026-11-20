
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

    return watches


def load_state():
    if not STATE_FILE.exists():
        return {"watches": {}}

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


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

    # Check unavailable phrases first.
    unavailable = [
        r"\bout\s+of\s+stock\b",
        r"\bsold\s+out\b",
        r"\bcurrently\s+unavailable\b"
    ]

    for pattern in unavailable:
        if re.search(pattern, page_text):
            return "OUT_OF_STOCK"

    if re.search(r"\bin\s+stock\b", page_text):
        return "IN_STOCK"

    raise RuntimeError(
        "Stock status unclear. Website may have changed."
    )


def monitor_watch(watch, state):
    watch_id = watch["id"]
    name = watch["name"]
    url = watch["url"]

    if not url.startswith("https://www.hmtwatches.in/"):
        raise ValueError(f"Invalid HMT product URL for {name}")

    print(f"\nChecking {name}...")

    current = check_stock(url)

    previous = state["watches"].get(watch_id)

    print(f"Previous: {previous}")
    print(f"Current: {current}")

    if previous != "IN_STOCK" and current == "IN_STOCK":
        send_telegram(
            f"🚨 HMT WATCH BACK IN STOCK! 🚨\n\n"
            f"Watch: {name}\n\n"
            f"Status: AVAILABLE\n\n"
            f"Buy now:\n{url}"
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

    # Save successful checks even if another watch failed.
    save_state(state)

    if errors:
        raise RuntimeError(
            "Some watches could not be checked: "
            + ", ".join(errors)
        )

    print("\nAll HMT watches checked successfully.")


if __name__ == "__main__":
    main()
