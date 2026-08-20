"""Preference loading, with the private values kept out of a public repo.

Behaviour (budget rules, exclusions, commute limit) stays in preferences.yaml
where it can be read and reviewed. The two values that identify the user —
income and home/work address — come from the environment instead, supplied as
GitHub Actions secrets.

Missing secrets fail loudly rather than degrading: an absent income silently
relaxes the rent cap, and an absent work address silently disables location
filtering entirely. Both would look like the bot working fine while sending
the wrong listings.
"""

import os

import yaml

PREFS_PATH = "preferences.yaml"
REQUIRED_ENV = ("ANNUAL_INCOME", "WORK_ADDRESS")


def require_env() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            f"missing required secret(s): {', '.join(missing)}. "
            "Set them with `gh secret set <NAME>` and add them to the workflow env."
        )


def load_prefs(path: str = PREFS_PATH) -> dict:
    with open(path) as f:
        prefs = yaml.safe_load(f)
    income = os.environ.get("ANNUAL_INCOME")
    if income:
        prefs["annual_income"] = float(income)
    return prefs
