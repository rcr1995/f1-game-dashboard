# F1 Game Dashboard

A bilingual Streamlit dashboard for exploring Formula 1 game leagues, race results, championship standings, circuit records, form, and all-time statistics from an Excel workbook.

![F1 Game Dashboard banner](assets/hero_banner.webp)

## Features

- Driver and constructor standings with F1-style tie-breakers
- Sprint points included in totals while race-only statistics remain accurate
- Championship progression, lead changes, momentum, and form tables
- Latest-race dashboard and calendar status
- Circuit win records and all-time title counts
- English and Portuguese interface
- Persistent dark and light themes
- Explicit workbook validation with actionable error messages
- A protected Admin area for importing race results from 2–4 screenshots

## Run locally

Python 3.11 is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Configure the Admin area once

Admin supports two server-side authentication modes: a password for a simple
single-administrator deployment, or OpenID Connect (OIDC). Select exactly one
with `admin_auth.mode`; there is no automatic fallback between them. Missing,
placeholder, or malformed selected-mode configuration leaves Admin closed;
settings for the inactive mode are ignored.

First, create a GitHub App, install it only on the workbook repository, disable
webhooks, and grant only **Repository contents: Read and write**. Generate a
private key and note the App and installation IDs. Then copy
`.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` locally, or paste
it into the deployment platform's server-side secret settings. Never commit
the real file; it is ignored by Git. For Streamlit Community Cloud, use
**App settings → Secrets**.

### Password mode

Generate a long, unique password and store only its Argon2id hash. With the
project dependencies installed, this command prompts without echoing the
password and prints the value to place in deployment secrets:

```powershell
python -c "from getpass import getpass; from argon2 import PasswordHasher; p=getpass('Admin password: '); print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16).hash(p))"
```

Configure:

```toml
[admin_auth]
mode = "password"
password_hash = "$argon2id$..."
```

Do not store the plaintext password. Authentication, the expiring session
grant, and an application-wide repeated-failure lockout are enforced
server-side. Sessions last 30 minutes by default and expire after 15 minutes of
inactivity. Five failed attempts within 15 minutes lock password attempts for
15 minutes across browser sessions on the running application instance.
Changing the configured hash invalidates existing grants.

Optional policy overrides are bounded: `session_ttl_seconds` accepts 300–28800,
`idle_ttl_seconds` accepts 60 through the configured session lifetime,
`max_failed_attempts` accepts 3–10, and `failure_window_seconds` and
`lockout_seconds` each accept 60–3600. Values outside these ranges fail closed.

### OIDC mode (recommended upgrade)

Create an OIDC web application with Google, Microsoft Entra ID, Auth0, Okta, or
another provider. Register `https://YOUR-DOMAIN/oauth2callback` as its redirect
URI (`http://localhost:8501/oauth2callback` locally), then configure:

```toml
[admin_auth]
mode = "oidc"
allowed_issuer = "https://accounts.google.com"
allowed_subject = "THE-ADMIN-IMMUTABLE-SUBJECT"
# allowed_email = "admin@example.com"

[auth]
redirect_uri = "https://YOUR-DOMAIN/oauth2callback"
cookie_secret = "A-LONG-RANDOM-SECRET-OF-AT-LEAST-32-CHARACTERS"
expose_tokens = false
client_id = "YOUR-OIDC-CLIENT-ID"
client_secret = "YOUR-OIDC-CLIENT-SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

The identity provider owns sign-in throttling and optional MFA. The app checks
the verified issuer and immutable `sub` claim on every protected action. An
optional `allowed_email` adds an exact match and requires the provider's
`email_verified` claim to be boolean `true`. Keep token exposure disabled and
enable MFA at the provider when available.

For either mode, fill every `[github]` value from the example and set
`F1_ENABLE_RACE_IMPORT = "1"` in deployment secrets or the server environment.
Leaving the flag absent or malformed disables Admin. It is safe to set the flag
before the remaining configuration: incomplete authentication or publisher
settings stop the page before upload, OCR, workbook access, or publication.
Restart the service after changing authentication or GitHub credentials.

The app's left menu remains collapsed by default. The public Dashboard route
still contains the same four tabs. The `/admin` route shows no upload, GitHub,
OCR, review, or write capability until the current session passes the selected
server-side authentication gate. GitHub configuration is also required;
incomplete or placeholder values close the updater. Logout clears the password
grant or OIDC identity session, remote workbook snapshot, approvals, uploads,
and all staged import data.

`admin_app.py` remains available as a phone-friendly compatibility entrypoint
for a separate Streamlit deployment. It routes to the same protected Admin page
and does not bypass authentication. Give that deployment its own server-side
secrets; in OIDC mode, register its own callback URL as well.

### Import Race and Sprint screenshots

After signing in as the configured admin, upload 2, 3, or 4 PNG/JPEG/WebP
screenshots from that event only. Admin pre-selects the uniquely active
championship and earliest unresolved `Upcoming` Calendar event; the editable
event controls stay collapsed unless that identity is ambiguous. The selected
red results tab then synchronizes **Race** or **Sprint** automatically when all
screenshots agree. Use the selected `RESULTS (RACE)` or `RESULTS (SPRINT)`
detail table, with repeated
rows between adjacent images so the set can be reconciled. Do not combine Race and Sprint in one
upload, and do not use `RESULTS (WEEKEND)`: the Weekend table is a points
summary and does not contain the `BEST` and `TIME` detail needed for import.
Detailed Sprint screens that use the same `GRID`/`STOPS`/`BEST`/`TIME`/`PTS`
layout as Race are handled identically, including total duration, gaps, lap
deficits, statuses, and fastest laps; the Sprint is still reviewed and
published separately from the Race.

After a Sprint is published, Admin resets to the same round's Race. After the
Race is published, it reloads the workbook and advances to the next unresolved
Calendar event. Missing, malformed, duplicated, or ambiguously mapped Calendar
data never guesses an identity; the editable event controls open for review.

The app validates size and image content, verifies the selected red results
tab, extracts every image, reconciles overlaps, and matches names only against
the controlled active roster. Position, driver, displayed result time/status,
and fastest-lap values are reviewed in the Admin editor. Low-confidence,
repaired, missing, or conflicting readings remain blocked for manual
correction. Points are re-derived from the workbook's verified race/sprint
scoring rules. Race and Sprint are approved and published separately, which
creates distinct `R` and `SR` result rows for the same weekend.
For a championship's first Sprint, the fixed project Sprint scale is available
only when its completed Race history exactly matches the verified project Race
scale; otherwise the import remains blocked for manual verification.

Nothing is published during upload, OCR, or review. Admin downloads the latest
GitHub workbook into an isolated temporary directory. Approval rechecks the
current admin identity, reviewed Git blob, event uniqueness, full roster,
teams, positions, and scoring; then it performs the preservation-oriented OOXML
transaction and publishes only the validated workbook with an optimistic blob
version check. Concurrent, duplicate, stale, or invented data is blocked and
must be reviewed again. After every OCR attempt the uploader is rotated and its
image bytes are discarded. A successful attempt retains only screenshot hashes
and review rows; a failed attempt retains only a one-shot text error and clears
any older review. Screenshots and credentials are never committed.

### League setup, roster changes, and corrections

The protected Admin task selector renders only one workflow at a time. **League
& roster setup** creates a new unique game/season/league identity, copies the
latest source roster for editing, accepts new drivers and teams, configures
complete Race and Sprint position points plus optional fastest-lap rules, and
builds an ordered Calendar including Sprint-weekend flags. The final preview is
bound to the reviewed GitHub blob and requires explicit approval. Publishing
adds configuration and Calendar rows without altering previous results; when a
configured league is active and every one of its managed Calendar rows is
already `Done`, the same transaction marks it Completed before activating its
successor. A league with unfinished rounds is blocked from being closed.

Configuration-backed leagues can also publish a complete roster snapshot from
a specified future round. Adding, removing, replacing, or moving a driver to a
different team therefore changes only that round and later rounds. Historical
events continue resolving the earlier snapshot. The same future snapshot may
revise complete Race/Sprint and fastest-lap rules for the new grid size. The UI
defaults to the next unpublished Calendar round and rejects any effective round
that already has results. Legacy leagues keep the manual Excel workflow for
roster changes; the next league can be brought under managed configuration
through the new-league wizard.

Each roster row may also contain optional **Alternative screenshot names**.
These reviewed spellings are copied into future leagues and round-effective
roster snapshots, and are used only to match OCR text to that exact configured
driver. An OCR name that is not the canonical driver name or one of these
controlled alternatives is never created automatically: it remains unresolved
until the admin selects an existing driver or first publishes a legitimate
roster change.

**Correct published event** selects one exact Calendar/result identity. Replace
requires 2–4 corrected screenshots and the same controlled OCR review, then
shows the currently published values beside the proposed replacement. Undo
shows every row being removed; undoing a Race restores only its exact Calendar
row to `Upcoming`, while undoing a Sprint does not change Calendar status. Both
operations create a new Git commit, preserve later events and the original
mistake in Git history, and require a source-versioned, digest-bound approval.
For an Active managed league, an undone scheduled Sprint automatically returns
as the next Sprint import while its completed Race remains intact. Completed or
Draft managed leagues allow replacement only, preventing unrecoverable gaps.

RapidOCR may download recognition models the first time extraction is used;
later extraction uses cached models. Editing `F1_Standings.xlsx` directly and
committing it through the existing manual Excel workflow remains fully
supported. Git history provides recovery for hosted publications.

The app automatically loads `F1_Standings.xlsx` from the repository root. It also searches the `data`, `Data`, `assets`, and `excel` directories when the default file is absent.

## Workbook format

The workbook must contain a worksheet named `Leagues` with these columns:

| Column | Meaning |
|---|---|
| `Game` | Game/version name |
| `Season` | Season label, such as `2026-T02` |
| `League Name` | League identifier |
| `Round` | Numeric round, or `All` for a season total |
| `GP Name` | Grand Prix name, or `All`/`Season Final` for a season total |
| `Driver` | Driver or player name |
| `Team` | Constructor name |
| `Finish Pos` | Numeric finishing position |
| `Points` | Numeric points earned |
| `Time` | Exact displayed total, gap, lap deficit, or status, such as `82:50.787`, `+0.946`, `+1 Lap`, or `DNF` |
| `Fastest Lap` | Exact displayed `BEST` value, such as `1:33.122`, or `N/A` when confirmed absent |

An optional `Type` column accepts `R` for a race and `SR` for a sprint. Unknown values are treated as races.

The optional `Calendar` worksheet supports:

- `League Name`
- `Round`
- `Date`
- `GP Name`
- `Circuit`
- `Status`
- `Time (Lisbon)`
- `Game`, `Season`, and immutable `League ID` for managed leagues
- `Has Sprint`

Managed leagues additionally use the locked `League Config`, `Roster Config`,
`Scoring Profiles`, and `Scoring Points` worksheets. These tables provide the
authoritative first-event roster, round-effective team assignments, Race and
Sprint scoring, and optional fastest-lap bonus eligibility. Older workbooks
without those sheets continue using verified result history and the manual
Excel workflow.

If `Calendar` is missing, standings remain available and the app displays a schedule-feature warning. Missing required sheets or columns, blank identifiers, invalid rounds, and non-numeric results stop loading with a clear message.

## Scoring behavior

- Points from race and sprint rows are added to championship totals.
- Wins, podiums, top-five finishes, average finish, and consistency use main-race rows only.
- Standings tie-break order is points, wins, podiums, average finish, then name.
- When race-level rows and season-total rows coexist, race-level rows are used to prevent double counting.
- Seasons with upcoming calendar entries are excluded from completed-title counts.

## Quality checks

Run the automated checks with:

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py admin_app.py dashboard_page.py admin_page.py admin_auth.py admin_management_ui.py dashboard_core.py league_config.py league_runtime.py league_workbook.py puskas_html.py race_correction.py race_import.py race_ocr.py race_workbook.py race_github.py race_import_ui.py
```

The GitHub Actions workflow runs these checks and performs a minimal Streamlit startup test for every push and pull request.

## Project structure

- `app.py` — public/Admin route and collapsed navigation
- `dashboard_page.py` — unchanged public dashboard presentation
- `admin_page.py` — fail-closed hosted Admin controller and phone-friendly UI
- `admin_app.py` — compatibility entrypoint to the same protected Admin route
- `admin_auth.py` — password/OIDC authorization, lockout, sessions, and logout-state clearing
- `admin_management_ui.py` — conditional league setup, roster snapshot, and correction workflows
- `dashboard_core.py` — workbook validation, normalization, and standings calculations
- `league_config.py` / `league_runtime.py` — managed roster and scoring models plus per-round authority
- `league_workbook.py` — preservation-oriented league/configuration transactions
- `race_correction.py` — approval-gated replacement and undo transactions
- `race_import.py` — controlled matching, reconciliation, and review validation
- `race_ocr.py` — lazy OCR and bounded raster-image validation
- `race_workbook.py` — approval-gated, serialized safe OOXML transaction
- `race_github.py` — short-lived GitHub App authentication and optimistic workbook publication
- `race_import_ui.py` — protected local/hosted 2–4 screenshot review workflow
- `puskas_html.py` — custom dashboard HTML rendering
- `tests/` — calculation and workbook regression tests
- `assets/` — optimized WebP dashboard imagery
