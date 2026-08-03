"""One-off Telegram delivery test. Not part of the poll pipeline."""

from .notify import send_telegram

INTRO = "Hi Caleb, merhaba Selin \U0001F44B\nHousing bot is wired up and can reach this group."

EXAMPLE_LISTING = """\
\U0001F534 CRITICAL — match 92/100

Prinsegracht 12, Den Haag
€1,950/mo · 75m² · 3 rooms

✨ Highlights: balcony, 5 min to station, quiet street
⚠️ Watch out: ground floor

Live 12 min ago · 2 responses so far
https://www.pararius.nl/huurwoning/den-haag/abc123/prinsegracht-12
"""

if __name__ == "__main__":
    send_telegram(INTRO)
    send_telegram(EXAMPLE_LISTING)
