"""Polls Telegram for commands sent in the group and acts on them.
Runs on its own short cron (see .github/workflows/telegram_commands.yml),
separate from the main poll-listings run."""

import json
import os
from pathlib import Path

import requests

OFFSET_PATH = "data/telegram_offset.json"

HELP_TEXT = (
    "Commands:\n"
    "/run — check for new listings right now, instead of waiting for the next automatic run (every 30 min)\n"
    "/help — show this message"
)


def _load_offset() -> int:
    p = Path(OFFSET_PATH)
    if not p.exists():
        return 0
    return json.loads(p.read_text()).get("offset", 0)


def _save_offset(offset: int) -> None:
    Path(OFFSET_PATH).write_text(json.dumps({"offset": offset}))


def _get_updates(offset: int) -> list:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def _reply(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def _trigger_poll_run() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/poll.yml/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"ref": "main"},
        timeout=10,
    )


def handle_command(command: str) -> None:
    if command == "/run":
        _trigger_poll_run()
        _reply("On it — checking for new listings now.")
    elif command == "/help":
        _reply(HELP_TEXT)


def handle_updates() -> None:
    offset = _load_offset()
    allowed_chat_id = os.environ["TELEGRAM_CHAT_ID"]

    for update in _get_updates(offset):
        offset = update["update_id"] + 1
        message = update.get("message") or update.get("channel_post")
        if not message or str(message["chat"]["id"]) != str(allowed_chat_id):
            continue
        text = message.get("text", "").strip()
        handle_command(text.split("@")[0])  # strip "@BotName" suffix used in groups

    _save_offset(offset)


if __name__ == "__main__":
    handle_updates()
