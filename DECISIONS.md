# Decision log

Why this bot is built the way it is. One entry per non-obvious decision, newest
first. Read this before changing behaviour — most of these were paid for with a
wrong alert or a failed run, and the reasoning isn't recoverable from the code.

Format: **date — decision**, then what forced it, and what would justify
revisiting. Keep entries short; the detail lives in the linked commit.

---

## 2026-08-20 — Feedback buttons dispatch a workflow rather than writing state
Phase 3. 👍/👎 on every alert; 👎 swaps the row for five canned reasons before
recording, because a bare rejection teaches the scorer nothing and free text
doesn't get typed on a phone. Decisions land in `data/feedback.json` and become
few-shot lines in the scoring prompt.
**The webhook can't write to the repo** — it's a Vercel function with no
checkout — so a tap dispatches `feedback.yml`, which commits. That reuses the
`GH_PAT` + dispatch path `/run` already uses instead of adding Vercel KV or a
database, and keeps one datastore.
**`feedback.yml` deliberately has no `concurrency:` group.** GitHub keeps only
one pending run per group, so two quick taps would cancel each other and lose a
decision. The push-retry loop is what makes concurrent runs safe.
**Callback data is a 6-byte hash, not the listing id** — Telegram caps
`callback_data` at 64 bytes. The listing is looked back up from
`seen_listings.json`, so feedback stores a pointer rather than a copy that could
drift; entries whose listing has been pruned are skipped rather than crashing.
**Albums lose their caption to a second message.** `sendMediaGroup` takes no
`reply_markup`, so a multi-photo alert sends photos uncaptioned and follows with
the caption carrying the buttons — rather than dropping the extra photos.

## 2026-08-20 — LLM scoring enabled; `test_message` is now the way to verify it
`ANTHROPIC_API_KEY` is set, so `score.py` is live (~$2–4/mo at current volume).
Verified against a fake listing: resolved €1450 kale + €75 servicekosten to
€1525 all-in, which is the extraction the feature exists for.
**Why the fake listing and not `test_scrape`:** `test_scrape` dedups against
real state, so once state is warm it sends nothing and therefore exercises
nothing — it could not have verified this. `test_message.py` (+ `test_message.yml`)
runs commute, scoring and Telegram against a hardcoded listing, touching no
state and fetching nothing, so it works regardless of what's in `seen`.
`test_scrape.yml` was also missing `ANTHROPIC_API_KEY` entirely — the workflow
we verify with would have silently scored nothing.
**Known wobble:** the score `reason` contradicted itself once on the income test
(said "fails" while quoting figures that pass). Cosmetic, in user-facing text;
revisit the prompt in `_prompt()` if it recurs on real listings.

## 2026-08-20 — Weekly heartbeat rides the poll run, not its own cron
Silence was ambiguous: "nothing matched" and "the bot is dead" looked identical,
and the 60-day scheduled-workflow auto-disable (plan §1, still unconfirmed with
`GITHUB_TOKEN` commits) fails exactly that way. `heartbeat.py` counts each run's
alerts and reports once a week.
**Not a separate scheduled workflow on purpose:** that cron would be disabled by
the same inactivity rule it exists to detect, so it would go quiet precisely when
it mattered. Riding `poll.yml` makes a missing heartbeat proof that polling
stopped.
Called *after* both state saves and skipped during quiet hours — it's the least
important thing in the run and must not cost the record of what was already sent,
nor fire a status report at 04:00. Counters accumulate in `data/heartbeat.json`,
which is byte-identical on zero-alert runs, so quiet runs still produce no commit.

## 2026-08-20 — Income and work address moved to Actions secrets
The repo is public and `preferences.yaml` carried `annual_income: 55000` while
`commute.py` hardcoded the work address — the plan (§1) called for keeping these
out of the tree and it hadn't been done. Only those two values moved; the rest
of `preferences.yaml` stays in the repo so filter behaviour remains readable
and reviewable.
`config.require_env()` fails the run when a secret is missing rather than
degrading: an absent income silently relaxes the rent cap, and an absent work
address silently disables location filtering entirely — both look like working
software while sending the wrong listings.
**Still outstanding:** both values remain in git history (they were committed
from 2026-08-03). Removing them needs a history rewrite (`git filter-repo`) and
a force-push; not done, because the income figure is low-sensitivity and the
rewrite breaks every existing clone and commit link.

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
- Phase 4 (application pre-fill from `tenant-docs/`) not started. User wants
  assist-only — no auto-submission of financial or ID documents.
- Whether `GITHUB_TOKEN` commits reset the 60-day scheduled-workflow inactivity
  timer is still unconfirmed (see the comment in `poll.yml`).
