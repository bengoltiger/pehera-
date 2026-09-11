# PEHRA — Predictive Early-warning for Hyperlocal Risk Assessment

**Smart India Hackathon 2026 · Problem SIH26077 — AI-Driven Hyper-Local Early Warning System for Severe Weather Nowcasting**

PEHRA is not a weather app and not a dashboard. It is a decision system that runs the
full chain end to end:

```
SIGNAL → EARLY SIGNAL → PREDICTION → CONFIDENCE → EXPLANATION → RISK
       → PRIORITY → WARNING → ACTION → OUTCOME → LEARNING
```

Every number on screen is produced by the backend risk engine and can be traced back to
a named input, with its source, age and quality. The UI computes no risk of its own.

---

## ⚠️ Data honesty (read this first)

**No live observation network is connected to this prototype.** Every environmental
value the *engine* consumes — rainfall, river level, soil moisture, wind, forecasts —
comes from deterministic simulated scenarios in `backend/app/simulation/`. This is
stated in the app itself on every screen, in every API response
(`data_mode.is_simulated: true`) and in every server-sent event.

The one external, real-time exception: the **Predict screen's atmosphere card** ingests
**live weather from Open-Meteo** (free, no API key) through a small server-side proxy
(`GET /api/live/weather`, 10-minute cache) and renders a real map with a live wind
particle field ("god's-eye view", canvas-2D — no WebGL, no new dependency). Those
measurements are labelled LIVE, the engine's simulated inputs are labelled ENGINE/SIM,
and if the provider is unreachable the card falls back to the simulated radar and says
so instead of pretending.

What that means concretely:

| Claim | Status |
|---|---|
| Risk engine, explanations, confidence, priority ranking | **Real code, real computation** |
| Alert decision engine, escalation, lifecycle, audit trail | **Real** |
| Prediction-vs-actual verification and skill scores | **Real computation, over simulated events** |
| Environmental observations and forecasts fed to the engine | **Simulated** — deterministic scenarios |
| Atmosphere card on the Predict screen | **Real live data** — Open-Meteo (temperature, wind field, rain), labelled LIVE |
| Push / SMS / e-mail delivery | **Simulated** — every record is prefixed `SIMULATED DELIVERY`, nothing leaves the machine |
| Population and infrastructure figures | **Demo estimates**, not census data |
| Accuracy against real weather events | **Never claimed** — the models are trained on simulated data and the app says so |

Forecast values are deliberately degraded by a forecast-skill decay model
(`backend/app/simulation/nowcast_error.py`) so verification cannot report a fake
perfect score. An earlier build accidentally read future ticks directly and reported
F1 = 1.000; that is fixed and must never be reintroduced.

---

## Design & themes

The UI follows the **"Mission Tactical Intelligence"** design system
(`docs/DESIGN.md`, exported from the team's Stitch project): dark operational
cockpit by default, **light "daylight console" theme** included — toggle from
the header (or the login screen). Both themes share one token set
(`frontend/src/index.css`); the GIS map canvas intentionally stays dark in
both, like a real ops workstation. Fonts: Plus Jakarta Sans (headlines),
Inter (body), JetBrains Mono (telemetry). Framer Motion drives page and card
animations and honours `prefers-reduced-motion`.

## Quick start

Requires Python 3.13+ and Node 20+.

```bash
# 1) backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000
# first start seeds the SQLite database (backend/pehra.db) idempotently
```

```bash
# 2) frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 — proxies /api to :8000
```

Single-port production mode:

```bash
cd frontend && npm run build     # emits ../backend/static
cd ../backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 8000
# open http://localhost:8000 — FastAPI serves the SPA and the API together
```

Interactive API docs: `http://localhost:8000/docs`.

### Demo accounts

| Username | Password | Role |
|---|---|---|
| `citizen` | `citizen123` | Citizen (home: Colaba, English) |
| `nagrik` | `citizen123` | Citizen (home: Kurla–Mithi, Hindi) |
| `authority` | `authority123` | BMC disaster management cell — command centre, alert approval |
| `admin` | `admin12345` | Administrator — audit log, system status |

Seeded credentials exist only because this is a prototype; they are listed by
`GET /api/auth/demo-accounts` and printed in the login screen.

### Reset

`POST /api/simulation/reset` (or the **Reset demo** button) restores a known state.
Deleting `backend/pehra.db*` and restarting rebuilds everything from seed.

---

## How the risk engine works

Two-dimensional risk — a dangerous hazard over an empty hillside is not the same
emergency as a moderate hazard over 190 000 people.

```
severity = Σ_family Σ_component  C[component] · w[component][feature] · norm(feature) · 100
overall  = severity · (0.72 + 0.28 · exposure/100)
```

* Components: hazard 0.60, vulnerability 0.15, forecast 0.25, plus a trend bonus ≤ 12.
* Missing features are **renormalised out**, never treated as zero.
* Compound risk adds ≤ 14 points when independent hazard families interact; hazards that
  describe the same physical event are not counted twice.

| Band | Range | Colour | Colour-blind pattern | ASCII |
|---|---|---|---|---|
| SAFE | 0–20 | `#1f7a4d` | solid | `OK` |
| LOW | 21–40 | `#3f7fbf` | dots | `·` |
| MODERATE | 41–60 | `#c98a17` | diagonal | `▲` |
| HIGH | 61–80 | `#d1600f` | cross | `▲▲` |
| CRITICAL | 81–100 | `#b3161c` | hatch | `■■■` |

**Confidence** = 0.32 data-quality + 0.30 model-confidence + 0.20 forecast-agreement +
0.18 historical-support, minus explicit penalties (−9 per missing required input,
−7 per stale input up to 3, ×0.55 on model fallback, −5 degraded link, −25 offline),
clamped to 22–96 %. Every penalty is shown with its reason.

**Uncertainty** ± = 3.0 + 22·(1−confidence) + 1.6·horizon, capped at 45 points.
Horizons: NOW, +30 m, +1 h, +2 h, +3 h, +6 h.

**Alerts** escalate WATCH ≥ 41 / WARNING ≥ 61 / CRITICAL ≥ 81 with 6-point hysteresis,
a 900 s cooldown and 3600 s deduplication, so the system cannot flap or spam.

**Priority** = risk × exposure × urgency × confidence, and the queue explains its own
ordering — at one point in the storm-surge scenario Kurla (risk 68, 390 k people)
outranks Colaba (risk 82, 230 k) and the UI says exactly why.

---

## Architecture

```
backend/
  app/
    core/         config.py, risk_config.py — every tunable in one place
    db/           SQLAlchemy models, session, idempotent seed
    providers/    adapter interface + demo implementations + registry
    simulation/   deterministic scenarios, forecast-skill decay
    engine/       normalisation, features, risk engine, confidence,
                  risk field, threat-cell detection & tracking
    riskmodels/   swappable models: demo (rules), statistical (ridge),
                  ml (gradient boosting) + trained artefacts
    alerts/       decision engine, channel adapters (all simulated)
    services/     prediction, alerts, orchestrator, clock, observability
    realtime/     server-sent event bus
    api/          57 REST endpoints
  scripts/        train_models.py, api_smoke.py, engine_smoke.py
frontend/
  src/
    lib/          typed API client, hooks (429 backoff), i18n, providers, theme
    components/   UI primitives, app shell, risk detail, map, radar canvas,
                  hero map, motion helpers, composer
    pages/        login, authority command centre (incl. SITREP + Predict),
                  citizen app (village defense, evacuation)
    test/         Vitest suites that run against the real API
docs/
  DESIGN.md       "Mission Tactical Intelligence" design system (Stitch export)
  DATASETS.md     production dataset roadmap (25 sources, grouped)
```

Provider adapters and risk models are registries: adding a real IMD feed or a new model
means implementing an interface and registering it, not editing the engine. Predictions
are snapshotted with the model name and version so old decisions stay explainable after
a model change.

**Stack** — FastAPI · SQLAlchemy · SQLite · scikit-learn · Vite · React 19 · TypeScript ·
Tailwind v4 · Leaflet · Recharts.

> The specification asked for Next.js. This prototype uses a Vite SPA served by FastAPI
> on one port, which fits a 2-CPU/2-GB environment; the component architecture is
> unchanged and the migration path is documented in `ARCHITECTURE.md` (in progress).

### Trained artefacts

| Model | Algorithm | Hold-out R² | MAE |
|---|---|---|---|
| `statistical.pkl` | Ridge regression, 37 features | 0.903 | 3.33 |
| `nowcaster.pkl` | Gradient boosting | 0.812 | 3.80 |

Trained on **simulated** scenario data via `python scripts/train_models.py`.
These numbers describe agreement with the reference engine on simulated events — they are
**not** real-world forecast accuracy.

### Verification (`POST /api/verify`)

| Scenario / ward | Result |
|---|---|
| mumbai_storm_surge / Colaba | simulated |
| mumbai_mithi / Kurla | simulated |
| mumbai_heatwave / Borivali | simulated |
| mumbai_normal | simulated |

MAE grows with lead time exactly as it should. All metrics describe agreement on
deterministic simulated data, not real-world forecasts.

---

## Scenarios

| Scenario | Behaviour |
|---|---|
| `mumbai_normal` | Flat ≤37 (LOW) — proves the system does not cry wolf |
| `mumbai_heavy_rain` | 29 → **76 HIGH at t7** → 24, sustained monsoon downpour |
| `mumbai_cloudburst` | 38 → **97 CRITICAL at t5** → 41, localised Dharavi–Kurla cloudburst |
| `mumbai_high_tide` | 38 → **92 CRITICAL at t8** → 43, rain + high tide compound |
| `mumbai_storm_surge` | 33 → **72 HIGH at t7** → 28, cyclonic surge at Colaba |
| `mumbai_mithi` | 40 → **93 CRITICAL at t11** → 43, Mithi river overflow at Kurla |
| `mumbai_compound` | 44 → **96 CRITICAL at t6** → 54, simultaneous rain + surge + Mithi |
| `mumbai_heatwave` | 45 → **80 CRITICAL at t11** → 50, heat dome pushes the suburbs to extreme heat |

24 ticks × 15 simulated minutes. The simulation lab can step the clock, jump to the
peak, cut connectivity, force any provider to fail, and swap the active model — so the
degraded and failure states can be demonstrated rather than described.

---

## Tests

```bash
cd backend  && PYTHONPATH=. .venv/bin/python scripts/api_smoke.py     # 57 endpoints
cd backend  && PYTHONPATH=. .venv/bin/python scripts/engine_smoke.py  # engine invariants
cd frontend && npm run test                                           # Vitest + jsdom (10 tests)
cd frontend && npx tsc -b && npx oxlint                               # types + lint
```

The frontend suite renders each route **against the running FastAPI process** instead of
mocked fixtures — mocks agree with whatever the UI assumes, and that is precisely the
class of bug (API shape drift) the suite exists to catch. It covers the authority
command centre, the new SITREP / Predict screens, the citizen app (both tabs), and
unauthenticated redirects. It skips itself with a clear message when the backend is not
up.

---

## Status

**Working today**

* Risk engine, confidence, uncertainty, momentum, compound risk, early-signal detectors
* Threat-cell detection, tracking and projected movement
* Priority queue with "why priority?", exposure and infrastructure impact
* Alert decision engine, human-in-the-loop approval, lifecycle audit trail, geofencing,
  simulated multi-channel delivery, acknowledgement funnel
* Alert composer with live citizen preview (EN/हिं)
* Prediction verification, replay and what-if APIs; swappable models with fallback
* 60 REST endpoints, SSE stream with polling fallback, JWT auth + RBAC, rate limiting
  (the client backs off and retries on 429)
* **Live external weather** (Open-Meteo, no API key) on the Predict screen: a
  server-side cached proxy (`/api/live/weather`) + a canvas-2D wind particle
  "god's-eye view" over a real map, with an honest simulated-radar fallback
* Authority UI: overview, **SITREP command & map**, **Predict / real-time telemetry feed**,
  hyperlocal map, priority queue, alerts console, simulation lab
* **Citizen app** (village defense + guided evacuation, mobile-first, EN/हिं account aware)
  wired to the same live engine
* Light + dark themes, Framer Motion transitions, tactical radar canvas of live cells

**Not built yet**

* Judge-demo guided tour, incidents / analytics / replay / system-status / audit screens
* PWA install + offline caching
* Backend pytest suite (`backend/tests/` is a stub; smoke scripts cover the API today)
* `ARCHITECTURE.md`

**Known limitations**

* Simulated data only — see the honesty table above.
* SQLite and an in-process rate limiter: single-node only, no horizontal scaling.
  The limiter default is 240 reads/min (`PEHRA_RATE_LIMIT_REQUESTS`); the busy demo
  box runs 600/min so the command centre and citizen app can poll together.
* Framer Motion + the new screens take the single-page bundle to ~740 kB raw
  (219 kB gzip) — fine for the demo; the Next.js migration path (see below) is where
  route-level code splitting comes back.
* Map tiles come from OpenStreetMap; when they cannot be reached the app detects it and
  falls back to its own vector basemap drawn from the seeded ward polygons, and says so
  on screen rather than showing a broken grey grid.
* Hindi coverage is UI chrome plus alert content; long engine narratives are English-first.

---

## Licence

Prototype built for SIH 2026. No licence has been chosen yet.
