# AccessPath — Confidence-Aware Accessible Route Planning

**A working local research/demo application.** A React + Leaflet frontend talks to a FastAPI + SQLite graph-routing backend. The project includes a **fully synthetic 20-node / 37-edge network** and needs **no accounts, API keys, map tile service, or external data** to demonstrate routing.

> **SAFETY NOTICE:** This project is an informational prototype, **not safety-certified navigation**. The sample paths, positions, and simulated verification states are fictional. Unverified paths can conceal barriers. Confidence scores are heuristic evidence indicators, **not calibrated real-world safety probabilities**. Never use its demo map to navigate a real environment.

## 1. Windows local setup (PowerShell)

### Requirements

- Windows 10/11 and VS Code
- **Python 3.12** (recommended for stable native dependencies)
- Node.js **20 or 22 LTS** and npm
- Git (for GitHub publication)

Check installations:

```powershell
py -0p
node --version
npm.cmd --version
git --version
```

If Python 3.12 is missing, install it from [python.org](https://www.python.org/downloads/) or:

```powershell
winget install -e --id Python.Python.3.12
```

Restart PowerShell after installation, then confirm `py -3.12 --version` works. **Do not use a broken default Python 3.15 installation:** `py -3.12` explicitly selects the installed 3.12 interpreter. If PowerShell blocks `npm.ps1`, use **`npm.cmd`**, as shown below.

Unzip **AccessPath.zip** to your Desktop; the folder inside the archive is `AccessPath`. Open the folder in VS Code via **File → Open Folder**.

**Terminal 1 — backend:**

```powershell
cd "$env:USERPROFILE\Desktop\AccessPath\backend"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\seed_demo.py --reset
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The first FastAPI startup also seeds an empty SQLite database automatically. Running `--reset` **erases all previous local reports, routing tests, moderation records, and evaluation runs**; use it only when you intentionally want a clean demo.

**Terminal 2 — frontend:**

```powershell
cd "$env:USERPROFILE\Desktop\AccessPath\frontend"
npm.cmd install
npm.cmd run dev
```

Open these links:

- **Frontend:** http://127.0.0.1:5173
- **API documentation / Swagger:** http://127.0.0.1:8000/docs
- **Health check:** http://127.0.0.1:8000/health
- **GeoJSON export:** http://127.0.0.1:8000/api/network.geojson

If you unzipped elsewhere, adapt the `cd` path. Keep both terminals running. The frontend Vite dev proxy automatically forwards `/api` requests to FastAPI; no frontend API key is required.

### Admin access — local demo ONLY

1. Click **Moderation** in the left navigation.
2. Enter `demo-admin-key` in the **Local demo access** input and click **Unlock dashboard**.
3. Review, verify, reject, resolve, or expire reports. Open **Evaluation lab** to run metrics using the same key.

The bundled default is deliberately a **demonstration secret**. For a custom local admin key, in Terminal 1 *before* launching the API:

```powershell
$env:ACCESSPATH_ADMIN_KEY = "replace-with-a-unique-long-secret"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Enter that same key in the frontend. **Do not deploy the demo admin setup publicly**. Replace it with actual user authentication, CSRF and abuse protection, rate limiting, privacy policies, and a data-provenance review system before real-world use.

## 2. Run tests and evaluation

From `AccessPath\backend` in a separate PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\evaluate.py
```

From `AccessPath\frontend`:

```powershell
npm.cmd run build
```

Tests cover graph connectivity, Dijkstra/A* cost equality across all node pairs and profiles, hard mobility barriers, uncertainty penalties, Yen alternatives, API validation, database persistence, pending-to-verified-to-resolved state transitions, auto-expiration, access control, and confidence calibration metric generation.

### Expected test scenario

- Select **Welcome Gate** → **Community Hub**, **Wheelchair**, uncertainty aversion 70%.
- The absolute shortest top path crosses a **synthetic confirmed staircase**, so its `unsuitable_segments` count is positive.
- AccessPath provides alternative routes without confirmed wheelchair hard barriers; unverified portions are visibly amber/dashed.
- Open **Community reports**, select a route segment on the map, and submit a report.
- **Pending** reports lower confidence, but do not automatically create a confirmed blockage.
- Use **Moderation** to **Verify** that obstruction. Reopen the planner; the verified obstruction is a hard constraint and the network revision increments.
- **Resolve** the report; that restriction is lifted. The route engine recalculates on the updated network.
- Run **Evaluation lab** to compute real routing metrics and an explicitly synthetic confidence-calibration experiment. Refresh the browser to see persisted evaluation data.

## 3. Algorithms and data model

| Module | Implementation |
| --- | --- |
| Shortest path | Custom heap-based Dijkstra; ignores accessibility barriers for baseline comparison |
| Accessibility route | Custom A* or Dijkstra with profile-specific hard barriers and soft risk penalties |
| A* heuristic | Great-circle lower-bound, scaled to remain admissible under stored edge lengths |
| Alternatives | Loopless Yen K-shortest paths, up to 5 through REST (3 in UI) |
| Edge accessibility | Distance, steps, slope, surface, curb, crossing, verification, survey timestamp, reviewed reports |
| Hard blockers | Verified obstructions and profile-specific stairs / curbs / slopes; unknowns are never marked confirmed-safe |
| Confidence | Edge evidence score from metadata completeness, verification, age, and pending reports; path confidence is the product of edge evidence scores |
| Adaptive routing | Edge-weighted uncertainty aversion; pending reports affect cost, verified barriers affect traversability, resolved/expired reports stop affecting either |
| Persistence | SQLite nodes, edges, reports, moderation audit, anonymous route requests, evaluation runs, revision counter |
| Geospatial | WGS84-coordinate synthetic GeoJSON; no external OSM or map tile requests |

The full equations, synthetic calibration assumptions, and limitations are documented in [docs/ALGORITHMS.md](docs/ALGORITHMS.md).

## 4. REST API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness and demo status |
| GET | `/api/network` | Nodes, edges, active reports, revision |
| GET | `/api/network.geojson` | GeoJSON feature collection |
| GET | `/api/profiles` | Hard constraint settings |
| POST | `/api/routes` | Distance baseline, accessibility routes, explanations, computed confidence |
| GET | `/api/reports` | Community report feed; optional `?status=verified` |
| POST | `/api/reports` | Submit pending obstacle report |
| POST | `/api/admin/reports/{id}/moderate` | Verify / review / reject / resolve / expire (admin header) |
| GET | `/api/admin/overview` | Moderation statistics + audit log (admin header) |
| POST | `/api/evaluations/run` | Compute and persist benchmark (admin header) |
| GET | `/api/evaluations` | Read prior computed benchmark runs |

Example API request from PowerShell (after the backend is running):

```powershell
$body = @{
  start_id = "N1"
  end_id = "N5"
  profile = "wheelchair"
  algorithm = "astar"
  risk_aversion = 75
  alternatives = 3
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/routes" -Method Post -ContentType "application/json" -Body $body
```

Example moderator request:

```powershell
$headers = @{ "X-Admin-Key" = "demo-admin-key" }
$body = @{ action = "verify"; note = "Confirmed in synthetic demonstration" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/reports/2/moderate" -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

Only use report IDs for which the requested state transition is valid. The documented `2` is just an example ID.

## 5. GitHub initialization and push

Create a **new empty GitHub repository** named `accesspath` under your account (do **not** preselect a GitHub README / gitignore / license). In the project root:

```powershell
cd "$env:USERPROFILE\Desktop\AccessPath"
git init
git branch -M main
git add .
git commit -m "Build AccessPath confidence-aware routing platform"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/accesspath.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME`. If Git identity is unconfigured:

```powershell
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

GitHub may prompt you to authenticate in the browser; **never put credentials or personal access tokens into source code**. A GitHub Actions workflow runs Python tests and a Vite build for every push / pull request. Database files, virtual environments, `node_modules`, build output, and secrets are ignored.

## 6. Screenshot checklist for your resume and GitHub

See [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md) for recommended browser sizes, exact UI states, file names, and Markdown embedding instructions. Capture actual running screenshots after launching the two services; do not submit synthetic mockups as application proof.

## 7. Source tree

```text
AccessPath/
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE
├── README.md
├── docs/
│   ├── ALGORITHMS.md
│   └── SCREENSHOTS.md
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── demo_data.py
│   │   ├── graph.py
│   │   ├── routing.py
│   │   ├── evaluation.py
│   │   ├── schemas.py
│   │   └── main.py
│   ├── scripts/
│   │   ├── seed_demo.py
│   │   └── evaluate.py
│   └── tests/
│       ├── conftest.py
│       ├── test_algorithms.py
│       └── test_api.py
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js
        ├── styles.css
        └── components/MapView.jsx
```

## 8. OpenStreetMap and licensing

**No OpenStreetMap data or OSM standard tile servers are currently used.** Synthetic sample nodes are deliberately not real pathways. GeoJSON is WGS84-coordinate and compatible with future import/export pipelines, but no live OSM importer is implemented.

If you later use real OSM data, comply with the [ODbL and required attribution](https://www.openstreetmap.org/copyright). If you later use `tile.openstreetmap.org`, comply with the [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/)—visible attribution, suitable caching, no bulk scraping/offline tile downloads, and application identification are required. OSM data typically does **not** verify accessibility on individual edges; retain unknown values unless actual inspection or trustworthy provenance supports them. **Do not render synthetic sample streets on top of real-world basemaps** as though they were real paths.

## 9. Resume bullets (update after your own runs)

- **Developed AccessPath**, a local-first React/Leaflet and FastAPI system for uncertainty-aware pedestrian routing using a persistent SQLite geospatial graph and customizable wheelchair/walker/step-free constraints.
- **Implemented custom Dijkstra and admissible A*** search plus Yen's K-shortest alternatives, enforcing verified obstacle and mobility-specific edge barriers while penalizing incomplete, stale, and unverified accessibility data.
- **Built community obstacle reporting, audited verification workflows, dynamic route invalidation, and synthetic confidence-calibration benchmarks**, with reproducible pytest coverage of search optimality and end-to-end moderation behavior.

For metrics, run `python scripts/evaluate.py` on your repository and cite the measured results together with **“on a synthetic network”**; never imply these represent verified physical safety or real-world user outcomes.
