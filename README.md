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

## Run locally

Python 3.11 is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### Update a race from two PlayStation screenshots

The public dashboard links to a separate private Streamlit updater. From a phone or computer, an approved user can upload exactly two screenshots, correct the extracted positions, and explicitly approve publication. The private updater downloads the latest workbook from GitHub, validates an isolated candidate, and publishes only `F1_Standings.xlsx` with an optimistic version check. Screenshots are never committed.

The hosted updater is `admin_app.py`. Deploy it as a **private** Streamlit Community Cloud app and keep its GitHub App credentials only in that app's Secrets settings:

```toml
[github]
owner = "rcr1995"
repository = "f1-game-dashboard"
branch = "main"
workbook_path = "F1_Standings.xlsx"
app_id = "YOUR_GITHUB_APP_ID"
installation_id = "YOUR_INSTALLATION_ID"
private_key = """YOUR_PRIVATE_KEY"""
```

The GitHub App should be installed only on this repository, with webhooks disabled and the minimum repository permission needed to update the workbook. A successful commit triggers the normal public Streamlit refresh. Concurrent or duplicate updates are blocked and must be reviewed again.

The original local Excel workflow remains available as a fallback. Enable the importer before starting Streamlit:

```powershell
$env:F1_ENABLE_RACE_IMPORT="1"
python -m streamlit run app.py
```

Open **Import race**, choose the championship and event, upload exactly two screenshots, and select **Extract standings**. The app matches names only against the active championship roster, calculates points from reviewed finishing positions, and requires explicit approval before it updates `F1_Standings.xlsx`. Uncertain OCR rows stay unresolved for correction.

RapidOCR may download its recognition models the first time extraction is used; later extraction uses cached models.

On approval, the app creates a recovery copy under `.codex-tmp/race-import-backups`, validates a temporary workbook, blocks duplicate events or stale reviews, and only then replaces the local workbook. Editing `F1_Standings.xlsx` directly remains fully supported.

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
python -m py_compile app.py admin_app.py dashboard_core.py puskas_html.py race_import.py race_ocr.py race_workbook.py race_github.py race_import_ui.py
```

The GitHub Actions workflow runs these checks and performs a minimal Streamlit startup test for every push and pull request.

## Project structure

- `app.py` — Streamlit interface and visual presentation
- `admin_app.py` — private phone-friendly hosted updater
- `dashboard_core.py` — workbook validation, normalization, and standings calculations
- `race_import.py` — controlled roster matching, screenshot reconciliation, and scoring validation
- `race_ocr.py` — optional offline screenshot OCR adapter
- `race_workbook.py` — approval-gated, preservation-oriented Excel transaction
- `race_github.py` — short-lived GitHub App authentication and protected workbook publication
- `race_import_ui.py` — local and hosted Streamlit review and approval workflow
- `puskas_html.py` — custom dashboard HTML rendering
- `tests/` — calculation and workbook regression tests
- `assets/` — optimized WebP dashboard imagery
