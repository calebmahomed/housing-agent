"""One-off: print transit minutes from candidate cities to Amsterdam, to decide
which belong in preferences.yaml's cities list. Not part of the poll pipeline."""

from .commute import _duration_minutes

CANDIDATES = [
    "Almere", "Lelystad", "Hilversum", "Amersfoort", "Leiden", "Gouda",
    "Alkmaar", "Hoorn", "Zwolle", "Apeldoorn", "Arnhem", "Nijmegen",
    "Deventer", "Breda", "'s-Hertogenbosch", "Tilburg", "Dordrecht",
    "Leeuwarden", "Groningen", "Enschede", "Maastricht",
]

if __name__ == "__main__":
    for city in CANDIDATES:
        minutes = _duration_minutes(f"{city}, Netherlands", "TRANSIT")
        print(f"{city}: {minutes} min" if minutes is not None else f"{city}: lookup failed")
