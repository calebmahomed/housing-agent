# Decision log

Why this bot is built the way it is. One entry per non-obvious decision, newest
first. Read this before changing behaviour — most of these were paid for with a
wrong alert or a failed run, and the reasoning isn't recoverable from the code.

Format: **date — decision**, then what forced it, and what would justify
revisiting. Keep entries short; the detail lives in the linked commit.

---

## 2026-08-19 — Telegram failures must never abort the run (`7e72e60`)
A 10s read timeout to `api.telegram.org` propagated out of `_post` through
`main()`, so poll run `32283629432` exited **before saving state** — losing the
record of everything it had already sent, which the next run would re-send.
`_post` now returns `False` on any exception; timeout raised to 30s because
Telegram fetches photo URLs itself on `sendPhoto`/`sendMediaGroup`.
**Rule this establishes:** delivery is best-effort, the state file is not.
Anything between "listing selected" and `save()` must not be able to raise.

## 2026-08-19 — Age limits need regexes, not literal phrases (`133eb90`)
Two Vesteda listings in Rijswijk were alerted on despite being 50+ housing.
The pages say `min.leeftijd 50 jaar` and `min. leeftijd 50 jr`; the age bound
varies by complex (50/55/65) and the punctuation varies too, so no list of
literal substrings covers it. Added `exclude_patterns` (regexes) alongside
`exclude_phrases`.
**Kept separate on purpose:** `"55+"` read as a regex means "5 followed by
one-or-more 5s", which matches a house number. Literal phrases stay literal.
Verified: 3 of 28 in-budget Vesteda listings are age-restricted.

## 2026-08-19 — No city whitelist; filter on commute time (`ec6fd61`)
A fixed list of 22 cities was silently dropping exactly the small commuter
towns that suit us — Rijswijk, Oegstgeest, Maassluis — and Vesteda writes Den
Haag as `'s-Gravenhage`, which no hand-maintained list would match. Replaced
with `max_commute_minutes: 90`, transit time to work via the Routes API.
Checked *before* the detail-page fetch (cheaper), and **fails open** so an API
outage can't silently hide listings.
**Revisit if:** the work address changes — it's `WORK_ADDRESS` in `commute.py`,
and the whole location filter is relative to it.

## 2026-08-19 — Vesteda: only `status == 1` is rentable (`ec6fd61`)
`POST /api/units/search` returns 523 units. Their own JS bundle maps
`getStatusName()`: 1 `nieuw`, 2 `verhuurd`, 3 `verhuurd onder voorbehoud`,
4 `gereserveerd`. Statuses 2–4 are ~80% of the feed and already gone.
Without this filter most alerts would be already-rented flats.

## 2026-08-19 — Seed undated sources instead of alerting (`ec6fd61`)
Vesteda publishes no date-added field, so on first sight its entire back
catalogue looks new (~28 in-budget listings at once). Sources in
`UNDATED_SOURCES` are recorded to state on first sight without alerting.
**Revisit if:** a source gains a real timestamp — then it can use
`max_age_hours` like the others and should leave that set.

## 2026-08-19 — Cap rent at €1400, below what income allows (`bb5cf8b`)
Income alone allows €1528 (55000/12/3). Set `max_rent: 1400` after a rejection
at €1450: clearing the landlord's income test is not the same as being a
competitive applicant, and losing those is wasted effort rather than a near
miss. `max_affordable_rent()` takes the stricter of the two, so the income
calc still applies if income changes.

## 2026-08-19 — Exclude parking spaces and storage (`bb5cf8b`)
The realtime-listings feed also rents parking and storage: `mainType: "other"`,
0 m², ~€150. Cheap enough to sail through the rent filter and be alerted as a
home. Now requires `mainType` in {apartment, house} **and** a non-zero
`livingSurface`.
**Pattern worth remembering:** every new source so far has shipped non-home
inventory or already-gone inventory in the same feed. Check for both.

## 2026-08-19 — Badge the source; direct beats aggregator (`a0ea8bc`)
Aggregator alerts (Pararius, Funda) arrive after the flat has been public a
while; a makelaar's own site is where we're likely first. Sources render as a
loud red `DIRECT — <name>` header vs a quiet blue/orange aggregator line. An
unmapped source defaults to the direct badge rather than silently looking like
an aggregator.
Scraped sources are also fetched **before** email ingest so cross-source dedup
suppresses the aggregator's later copy of the same flat, not the other way
round.

## 2026-08-19 — Prefer a shared platform feed over per-site scrapers (`056f03b`, `bb5cf8b`)
`verra.nl` and `estata.nl` run the same "realtime-listings" website product,
serving the whole catalogue as JSON at `/en/realtime-listings/consumer`. Each
new agency on it costs one line in `PLATFORM_SITES`, not a scraper.
Probed ~40 agency/landlord sites on 2026-08-19: only those two use it.
123Wonen, vb&t, HouseHunting, Domica and Inter Immo all render client-side and
would each need a Playwright + selector adapter — the per-site maintenance the
plan warned about. Holland2Stay is Cloudflare-blocked.
**How the good endpoints were found:** reading the page's JS bundle for the
XHR it makes (that's how both the platform feed and Vesteda's
`/api/units/search` turned up). Do that before hand-writing selectors.

## 2026-08-19 — LLM scoring built but dormant (`056f03b`)
`score.py` makes one Claude call per surviving listing (resolves kale vs.
inclusief rent, fills missing size/bedrooms, adds a 1–10 score and one line of
why), reusing the page text the exclusion check already fetched so there's no
second page load. Deferred on cost grounds: it returns `None` when
`ANTHROPIC_API_KEY` is unset and the caption simply omits the score line.
**To enable:** add the GitHub secret. No code change.

## 2026-08-19 — Test sends must not consume real listings (`3cab708`, `f873b9c`)
`test_scrape.yml` runs the real pipeline against live data but never saves
state, so a test send can't stop the real poll from alerting on that listing
later. It also skips the Chromium install: scraped makelaar pages are plain
HTML, and the Playwright fallback exists only for Cloudflare-guarded aggregator
pages this workflow never fetches. That step also hung on apt for 10+ minutes.

## 2026-08-04 — Playwright only for Cloudflare-guarded pages (`844c39f`)
Pararius and Funda detail pages sit behind a JS challenge a plain request can't
pass (verified: bare `curl` gets a 403 "Just a moment..." page). `detail_check`
tries plain HTTP first and falls back to headless Chromium.
This is a deliberate workaround of an anti-bot control, accepted after
discussing the tradeoff — **not** a default to copy into other scraping
contexts without the same conversation.

## 2026-08-04 — `/catchup` recovery path (`d4ac825`)
A failed state commit (e.g. a git push race) could consume emails without
recording them. `/catchup` re-scans recent mail rather than only unseen mail.
Shares `main.prepare()` with the poll run so the two can't drift apart.

## 2026-08-04 — Telegram commands via webhook, not cron polling (`0a101ab`)
GH Actions cron polling for bot commands was unreliable; replaced with a real
webhook (Vercel function in `telegram-webhook/`).

## 2026-08-04 — Parse Pararius from HTML, not the text part (`6ecdc58`)
A manual Outlook forward regenerates the body from HTML and mangles `€`/`²`/`·`
into U+FFFD. Parsing the HTML part survives it. Verified against real captured
alert emails; both are kept as fixtures.

## 2026-08-03 — Income-based rent cap, not a flat number (`b8a72eb`)
Dutch landlords typically require gross monthly income ≥ 3× rent, so the
binding constraint is derived from income rather than picked. Later joined by
the stricter `max_rent` (above).

## 2026-08-03 — Filter on `total_monthly`, not `rent` (`0ed52a6`)
Listings are wildly inconsistent about kale huur vs. inclusief. A €1,950 flat
with €300 servicekosten is €2,250 in practice. Every budget comparison uses
`total_monthly`.

## 2026-08-03 — State as JSON committed back to the repo (`0ed52a6`, `00450d1`)
The runner is ephemeral. Committing `data/seen_listings.json` sidesteps the
persistence problem rather than working around it. Pushes retry on rejection
because a concurrent commit shouldn't drop a run's state update.
**Revisit if:** the JSON files or the commit history become unwieldy — then a
free Postgres tier, per the plan.

---

## Known gaps

- `parse_funda` is still best-guess regex; never validated against a real Funda
  alert email. `parse_pararius` was fixed against real captured mail and has
  fixtures — Funda needs the same treatment.
- No weekly heartbeat to Telegram, so silence is indistinguishable from
  "no matches".
- Phase 4 (application pre-fill from `tenant-docs/`) not started. User wants
  assist-only — no auto-submission of financial or ID documents.
- Whether `GITHUB_TOKEN` commits reset the 60-day scheduled-workflow inactivity
  timer is still unconfirmed (see the comment in `poll.yml`).
