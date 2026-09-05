# F1 Game Dashboard

A bilingual Streamlit dashboard for exploring Formula 1 game leagues, race results, championship standings, circuit records, form, and all-time statistics from an Excel workbook.

![F1 Game Dashboard banner](assets/hero_banner.webp)

## Features

- Driver and constructor standings with F1-style tie-breakers
- Sprint points included in totals while race-only statistics remain accurate
- Championship progression, lead changes, momentum, and form tables
- Latest-race dashboard and calendar status, with completed-Race standings on hover, focus, or tap
- Circuit win records and all-time title counts
- English and Portuguese interface
- Persistent dark and light themes
- Explicit workbook validation with actionable error messages
- A protected Admin area for importing race results from 2–4 screenshots
- A protected, validation-gated download of the latest GitHub Excel workbook

## Run locally

Python 3.11 is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Isolated Vercel hosting trial

`Dockerfile.vercel` and `vercel.json` run the existing Streamlit application
using Vercel's container runtime. No frontend rewrite or workbook conversion is
involved. This trial belongs to the separate `f1puskasleague` project on the
`styrgo` team; it does not replace the Streamlit Community Cloud deployment.

The image intentionally defaults to `F1_ENABLE_RACE_IMPORT=0`. Without approved
server-side Google/GitHub configuration, `/admin` stays closed and cannot upload
screenshots or publish workbook changes. The public page now reads the same
`F1_Standings.xlsx` from `rcr1995/f1-game-dashboard`, branch `main`, using anonymous
read-only requests. It checks for updates every minute while open and on a new
visit (with a 60-second server cache). Valid changes refresh the dashboard data
without an app reboot. Network/GitHub delays can extend this interval.

Manual editing is still supported: download the workbook, edit it in Excel, and
upload/commit it back to the same path on `main`. Preserve required sheet names,
column headings, and identifiers. Invalid or unavailable updates leave the last
valid snapshot visible with a warning; the source workbook is never rewritten
by the public reader. The bundled workbook is only a first-start fallback.

In the authenticated Admin area, **Get latest Excel** performs a new server-side
GitHub fetch and validates that exact snapshot before presenting its download.
It does not change or publish the workbook and does not interrupt an open race
review. Public and unauthorized routes never render this control.

`F1_PUBLIC_GITHUB_SYNC=1` enables this behavior for the container. Other deployments
and local runs retain their original local-file workflow unless explicitly
enabled. Optional `F1_PUBLIC_GITHUB_OWNER`, `F1_PUBLIC_GITHUB_REPOSITORY`,
`F1_PUBLIC_GITHUB_BRANCH`, and `F1_PUBLIC_GITHUB_WORKBOOK_PATH` select another public
workbook. Admin publishing must target exactly the same source when sync is on.
The read cache is bounded, validated, atomically replaced, and kept outside the
repository. No GitHub credentials or Excel write endpoint are exposed publicly.

The language selector remembers only `en` or `pt` in the visitor's browser using
the app-owned key `f1puskasleague.language.v1`. It applies to Dashboard and Admin
on the same site. A different browser/domain, cleared storage, private browsing,
or blocked local storage may require choosing the language again. No login or
authentication information is stored by this preference component.

The source upload and container context use strict allowlists. Local secrets,
`.env*`, `.codex*`, private keys, temporary screenshots, Git metadata, and local
outputs are excluded. Do not replace those allowlists with a broad copy of the
workspace. Sharing the production GitHub App key with this separate host requires
the owner's explicit approval, because approved Admin actions will then change
the shared workbook and affect both dashboards.

To validate packaging and deploy from an authenticated Vercel CLI session:

```powershell
python -m unittest discover -s tests -p test_vercel_packaging.py -v
npx --yes vercel@59.11.2 link --project f1puskasleague --scope styrgo
npx --yes vercel@59.11.2 deploy --dry --json --scope styrgo
npx --yes vercel@59.11.2 deploy --scope styrgo
```

Check that the dry run reports the **Container** framework and only expected
runtime files before uploading. Vercel assigns a new project's first deployment
to its production environment; this is still only the isolated trial project,
not the existing live dashboard. Later CLI deployments default to previews.

Before considering a hosting switch, verify cold starts, WebSocket reconnects,
filter interactions, mobile rendering, and real upload/review flows. Container
and WebSocket support are beta. The Vercel Admin therefore uses the bounded
WebSocket screenshot component described below instead of Streamlit's
instance-local HTTP uploader. Admin validation requires separate test-only
authentication and a sandbox workbook publisher or test-only GitHub repository
and GitHub App. Do not publish fabricated results to test hosting. Vercel
usage is charged against the existing plan; a separate project is not a promise
of zero additional usage cost.

### Enable the Vercel Admin after authorization

Use Vercel's **server-side sensitive environment variables**, scoped to the
`f1puskasleague` project's intended deployment environment, never a public/client
variable or a build argument:

1. Add `F1_STREAMLIT_SECRETS_TOML` containing the existing `[admin_auth]`, `[auth]`,
   and `[github]` configuration described below. Retain the immutable Google
   issuer/subject allowlist. Use a new random cookie secret for this host and set
   `auth.redirect_uri` to `https://f1puskasleague.vercel.app/oauth2callback`.
2. Register that additional exact callback in the Google OAuth web client,
   keeping the original Streamlit callback. Do not change who is allowed Admin.
3. Set `F1_ENABLE_RACE_IMPORT=1` as a separate deployment environment variable
   and redeploy this project. A legacy root flag in the TOML is ignored; the
   deployment flag is authoritative. `F1_PUBLIC_DASHBOARD_URL` controls return
   links and defaults to the Vercel URL in this container image.

`vercel_start.py` validates the secret bundle without logging it, writes it to a
private runtime-only temporary file (0700 directory/0600 file on Linux), removes
the raw bundle from the child environment, and starts Streamlit using only that
secret file. Missing/bad configuration never grants access. Do not paste secrets
into commands, source, screenshots, browser-local storage, or build logs. Verify
Google login, unauthorized direct access, logout, and screenshot review on the
host before relying on it. Preview and production credentials are separate;
never weaken preview protection to make an OAuth test work.

The Vercel launcher also installs `vercel_upload_gate.py` before starting the
pinned Streamlit 1.59.2 server. Native screenshot PUT/DELETE requests must have
both a live, server-authenticated Admin session and a valid signed Google login
cookie for this exact origin, before their body is read. Missing, expired,
forbidden, or logged-out identities cannot call that underlying HTTP route.
Vercel does not guarantee that those separate requests reach the container
holding the Streamlit session, so `F1_WEBSOCKET_SCREENSHOT_UPLOAD=1` replaces
the two protected screenshot pickers with `secure_image_upload.py`. It sends
2–4 images over the already-authenticated Streamlit connection and validates
the count, PNG/JPEG/WebP type and signature, filename, declared and decoded
size, SHA-256, duplicates, session context and one-time submission on both
sides. Limits are 12 MiB per image and 25 MiB per set. Bytes remain only in the
Admin session and are removed after OCR, errors, context changes and logout;
normal Streamlit session expiry handles abandoned browser sessions. Standard
`streamlit run app.py` keeps the native uploader, and manual workbook editing
is unaffected. The Vercel picker shows verified filenames and sizes instead of
Streamlit's instance-local image preview URLs. Both version-pinned paths fail
closed; re-audit them before upgrading Streamlit.

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

While an authenticated Admin corrects a result, the four editable fields are
also checkpointed for seven days as one encrypted, integrity-protected token in
that browser. This lets the same authorized identity recover after a websocket
disconnect or container restart without retaining screenshots. The token is
bound to the exact workbook version and event context, cannot restore for a
different identity, and contains no OCR text or publication approval. It is
cleared after publication, an explicit discard, workbook refresh, or logout
from an active Admin session. Signing out only to renew an expired/forbidden
identity session preserves the encrypted draft for the same authorized Admin.

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

The season code is generated automatically as `YYYY-TNN`. `YYYY` comes from
the selected season-start year (and is rechecked against the earliest reviewed
Calendar date); `NN` is one above the highest existing season number for that
year. With the current workbook, the next 2026 league therefore starts as
`2026-T03`. Conflicting ownership or malformed historical codes block the
preview instead of guessing.

The **Define future driver–team lineup** task publishes a complete roster
snapshot from a specified future round. This is where the administrator defines
which drivers will race and for which teams. Adding, removing, replacing, or
moving a driver to a different team therefore changes only that round and later
rounds. Historical events continue resolving the earlier snapshot. The same
future snapshot may revise complete Race/Sprint and fastest-lap rules for the
new grid size. The UI defaults to the next unpublished Calendar round and
rejects any effective round that already has results. Legacy leagues keep the
manual Excel workflow for roster changes; the next league can be brought under
managed configuration through the new-league wizard.

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

The repository workbook is Pivot-free. The dashboard does not use an Excel
Pivot worksheet: standings and records are calculated directly from `Leagues`.
A legacy workbook can be converted to the smaller Pivot-free package without
rewriting any retained worksheet, formula, helper column, comment, or style:

```powershell
python -m workbook_simplify F1_Standings.xlsx F1_Standings.simplified.xlsx
```

The output path must be new. The command validates all package relationships,
blocks removal if a retained formula, data validation, conditional format, or
hyperlink still references `Pivot`, and leaves the source untouched. The app's
race-import, correction, league-setup, and manual Excel workflows accept both
legacy and Pivot-free workbooks.

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
python -m py_compile app.py admin_app.py dashboard_page.py admin_page.py admin_auth.py admin_management_ui.py dashboard_core.py league_config.py league_runtime.py league_workbook.py puskas_html.py race_correction.py race_import.py race_metadata.py race_ocr.py race_workbook.py race_github.py race_import_ui.py workbook_simplify.py
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
- `race_metadata.py` — mixed-version-safe event metadata and writer API guard
- `race_ocr.py` — lazy OCR and bounded raster-image validation
- `race_workbook.py` — approval-gated, serialized safe OOXML transaction
- `workbook_simplify.py` — deterministic, recovery-backed removal of obsolete Pivot artifacts
- `race_github.py` — short-lived GitHub App authentication and optimistic workbook publication
- `race_import_ui.py` — protected local/hosted 2–4 screenshot review workflow
- `review_draft_recovery.py` — encrypted browser-local recovery for unfinished reviews
- `puskas_html.py` — custom dashboard HTML rendering
- `tests/` — calculation and workbook regression tests
- `assets/` — optimized WebP dashboard imagery
