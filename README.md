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

Admin uses Streamlit's server-side OpenID Connect (OIDC) authentication. There
is no application password to leak or brute-force: the identity provider owns
sign-in, throttling, and optional MFA, while this app checks the verified token
against one exact administrator identity on every protected action.

1. Create an OIDC web application with Google, Microsoft Entra ID, Auth0, Okta,
   or another OIDC provider. Register `https://YOUR-DOMAIN/oauth2callback` as
   its redirect URI (`http://localhost:8501/oauth2callback` for local use).
2. Create a GitHub App, install it only on the workbook repository, disable
   webhooks, and grant only **Repository contents: Read and write**. Generate a
   private key and note the App and installation IDs.
3. Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` locally,
   or paste it into the deployment platform's server-side secret settings.
4. Fill all fields in `[auth]`, `[admin_auth]`, and `[github]`. Generate a strong
   random `auth.cookie_secret`; set the exact provider issuer and the admin's
   immutable OIDC `sub` claim. An optional `allowed_email` adds an exact match
   and requires the provider's `email_verified` claim to be boolean `true`.
5. Set `F1_ENABLE_RACE_IMPORT = "1"` in deployment secrets or the server
   environment. Leaving it absent or malformed disables Admin fail-closed.
   Restart the service after changing authentication or GitHub credentials.

Never commit `.streamlit/secrets.toml`; it is ignored by Git. For Streamlit
Community Cloud, use **App settings → Secrets**. Keep token exposure disabled.
Use a single-tenant/test-user allowlist and enable MFA at the provider when
available.

The app's left menu remains collapsed by default. The public Dashboard route
still contains the same four tabs. The `/admin` route shows no upload, GitHub,
OCR, review, or write capability until the current OIDC identity passes the
exact server-side allowlist. GitHub configuration is also required; incomplete
or placeholder values close the updater. Logout clears the identity cookie,
remote workbook snapshot, approvals, uploads, and all staged import data.

`admin_app.py` remains available as a phone-friendly compatibility entrypoint
for a separate Streamlit deployment. It routes to the same protected Admin page
and does not bypass OIDC. Configure that deployment's own callback URL and the
same server-side secrets.

### Import race screenshots

After signing in as the configured admin, upload 2, 3, or 4 PNG/JPEG/WebP
screenshots from one race. The app validates size and image content, extracts
each image, reconciles overlaps, and matches names only against the controlled
active roster. Low-confidence or ambiguous readings remain blocked for manual
correction. Points are re-derived from the workbook's verified race/sprint
scoring rules.

Nothing is published during upload, OCR, or review. Admin downloads the latest
GitHub workbook into an isolated temporary directory. Approval rechecks the
current admin identity, reviewed Git blob, event uniqueness, full roster,
teams, positions, and scoring; then it performs the preservation-oriented OOXML
transaction and publishes only the validated workbook with an optimistic blob
version check. Concurrent, duplicate, stale, or invented data is blocked and
must be reviewed again. Screenshots and credentials are never committed.

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

An optional `Type` column accepts `R` for a race and `SR` for a sprint. Unknown values are treated as races.

The optional `Calendar` worksheet supports:

- `League Name`
- `Round`
- `Date`
- `GP Name`
- `Circuit`
- `Status`
- `Time (Lisbon)`

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
python -m py_compile app.py admin_app.py dashboard_page.py admin_page.py admin_auth.py dashboard_core.py puskas_html.py race_import.py race_ocr.py race_workbook.py race_github.py race_import_ui.py
```

The GitHub Actions workflow runs these checks and performs a minimal Streamlit startup test for every push and pull request.

## Project structure

- `app.py` — public/Admin route and collapsed navigation
- `dashboard_page.py` — unchanged public dashboard presentation
- `admin_page.py` — fail-closed hosted Admin controller and phone-friendly UI
- `admin_app.py` — compatibility entrypoint to the same protected Admin route
- `admin_auth.py` — OIDC claim authorization and logout-state clearing
- `dashboard_core.py` — workbook validation, normalization, and standings calculations
- `race_import.py` — controlled matching, reconciliation, and review validation
- `race_ocr.py` — lazy OCR and bounded raster-image validation
- `race_workbook.py` — approval-gated, serialized safe OOXML transaction
- `race_github.py` — short-lived GitHub App authentication and optimistic workbook publication
- `race_import_ui.py` — protected local/hosted 2–4 screenshot review workflow
- `puskas_html.py` — custom dashboard HTML rendering
- `tests/` — calculation and workbook regression tests
- `assets/` — optimized WebP dashboard imagery
