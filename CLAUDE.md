# housing-agent

Dutch rental-hunting bot: scrape sources + IMAP alert emails → filter → dedup →
Telegram. Runs on GitHub Actions (`poll.yml`, 30-min cron), commits
`data/seen_listings.json` back as its memory. Nothing runs locally.

## Read first

**`DECISIONS.md` is the context file.** Read it before changing behaviour. Most
entries were paid for with a wrong alert or a failed run, and the reasoning is
not recoverable from the code.

**Append to it whenever you make a decision the code won't explain**: a filter
threshold, a source quirk, a workaround, something deliberately *not* built.
Newest first, same format as existing entries — what forced it, and what would
justify revisiting. One or two entries per session is right; if you're logging
every edit you're logging too much. Skip it for mechanical changes.

## Layout

| Path | What |
|---|---|
| `housing_agent/scrape.py` | Direct sources: shared platform feed (verra, estata), Vesteda, ikwilhuren |
| `housing_agent/ingest.py` | IMAP parsing of Pararius/Funda alert emails |
| `housing_agent/main.py` | `prepare()` is the per-listing pipeline, shared with `/catchup` |
| `preferences.yaml` | Budget, commute limit, exclusions. Behaviour lives here, not in code |
| `test_housing_agent.py` | Plain asserts, no framework: `python test_housing_agent.py` |

## Conventions

- **Verify with a real run, not "should work".** `gh workflow run test_scrape.yml`
  runs the real pipeline read-only (never saves state), so a test send can't
  consume a listing the real poll should alert on.
- **Fail open on lookups, never on state.** Commute, detail-page fetch and
  scoring all degrade to "unknown" rather than dropping a listing. Conversely
  nothing between selecting a listing and `save()` may raise — a Telegram
  timeout once aborted a run before it saved.
- **New source? Check for non-home and already-gone inventory in the same
  feed.** Every source so far has shipped parking spaces, storage, or rented
  units alongside real listings.
- **Look for the JSON endpoint before writing selectors.** Read the page's JS
  bundle for the XHR it makes — that's how the platform feed and Vesteda's
  `/api/units/search` were found.
- `ponytail:` comments mark deliberate shortcuts with a known ceiling.
