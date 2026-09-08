"""Fit PEHRA's swappable risk models on the deterministic demo engine.

    cd backend && PYTHONPATH=. .venv/bin/python -m scripts.train_models

Two artefacts are produced under ``app/riskmodels/artefacts/``:

``statistical.pkl``
    Ridge regression that maps a *normalised feature vector* to the reference
    engine's compound severity index. It learns the engine's own composition
    rule, so it can stand in for the engine and degrade smoothly when inputs
    are missing (the vector carries explicit missingness flags).

``nowcaster.pkl``
    Gradient-boosting regressor that maps *present* conditions plus a requested
    lead time to the severity index that will actually be observed at that lead
    time. It never sees the forecast feed, so it is a genuine nowcasting
    formulation rather than a re-scoring of a known future.

────────────────────────────────────────────────────────────────────────────
DATA HONESTY
Both models are fitted on PEHRA's deterministic *simulated* scenarios. Their
metrics measure how well they reproduce the reference engine / the simulated
future — never real-world forecasting skill. That caveat is stored inside the
artefact metadata and surfaced everywhere the metrics are displayed.
────────────────────────────────────────────────────────────────────────────

Generalisation is measured with a **grouped split by location**: three wards
are held out entirely, so the test score reflects performance on terrain the
model never saw, not on memorised rows.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pickle
import random
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.core.risk_config import DEFAULT_HORIZONS_MIN
from app.db.models import Location
from app.db.seed import seed_all
from app.db.session import init_db, session_scope
from app.engine.features import assemble_features
from app.engine.normalise import normalise
from app.engine.risk_engine import compute_compound, score_hazard
from app.providers.base import ProviderContext
from app.riskmodels.statistical import FEATURE_ORDER, build_vector
from app.simulation.nowcast_error import degrade_field
from app.simulation.scenarios import SCENARIOS

ARTEFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app", "riskmodels", "artefacts")

#: features a real deployment loses most often — dropped in augmented samples so
#: the missingness flags actually carry signal.
DROPPABLE = ["river_level_ratio", "river_rate", "cloud_top_temp_k", "lightning_rate",
             "soil_moisture", "forecast_rain_3h", "rain_accumulation_3h"]

HOLDOUT_LOCATIONS = {"loc_hadapsar", "loc_mulshi", "loc_junnar"}


# ---------------------------------------------------------------------------
# Sample generation
#
# Samples are produced through the REAL provider pipeline (`assemble_features`)
# rather than a re-implementation of it, so the training distribution is
# exactly the inference distribution — including scenario outages, structurally
# absent river gauges and every provider quirk.
# ---------------------------------------------------------------------------
def severity_of(loc: Location, raw: Dict[str, Optional[float]]) -> float:
    norm = {k: normalise(k, v) for k, v in raw.items()}
    hazards = list(loc.primary_hazards or ["flood"])
    results = [score_hazard(h, norm, raw) for h in hazards]
    return compute_compound(results).compound_severity


def drop_features(raw: Dict[str, Optional[float]], rng: random.Random, n: int) -> Dict[str, Optional[float]]:
    out = dict(raw)
    for feat in rng.sample(DROPPABLE, k=min(n, len(DROPPABLE))):
        out[feat] = None
    return out


def collect_raw(scenario, locations: List[Location]) -> Dict[Tuple[str, int], Dict[str, Optional[float]]]:
    """raw feature dict for every (location, tick) of a scenario."""
    base = dt.datetime(2026, 1, 1)
    table: Dict[Tuple[str, int], Dict[str, Optional[float]]] = {}
    for tick in range(scenario.total_ticks):
        ctx = ProviderContext(
            now=base + dt.timedelta(minutes=tick * scenario.tick_minutes),
            scenario_id=scenario.id, tick=tick,
        )
        for loc in locations:
            table[(loc.id, tick)] = assemble_features(loc, ctx).raw_dict()
    return table


def build_datasets(locations: List[Location]) -> Tuple[dict, dict]:
    """Return (statistical_dataset, nowcaster_dataset)."""
    rng = random.Random(20260908)
    stat_X, stat_y, stat_g = [], [], []
    now_X, now_y, now_g = [], [], []

    for scenario in SCENARIOS.values():
        print(f"    scenario {scenario.id} …", flush=True)
        table = collect_raw(scenario, locations)
        for loc in locations:
            for tick in range(scenario.total_ticks):
                present_raw = table[(loc.id, tick)]

                for horizon in DEFAULT_HORIZONS_MIN:
                    ticks_ahead = int(round(horizon / scenario.tick_minutes))
                    target_tick = min(tick + ticks_ahead, scenario.total_ticks - 1)
                    truth_raw = table[(loc.id, target_tick)]

                    # --- statistical: learn the engine's composition rule ----
                    # Paired with the SKILL-DEGRADED forecast vector, because
                    # that is exactly what the model is handed at inference.
                    fc_raw = degrade_field(truth_raw, present_raw,
                                           horizon_minutes=horizon,
                                           key=(scenario.id, loc.id, tick))
                    variants = [fc_raw, drop_features(fc_raw, rng, rng.randint(1, 3))]
                    for variant in variants:
                        norm = {k: normalise(k, v) for k, v in variant.items()}
                        stat_X.append(build_vector(norm, horizon))
                        stat_y.append(severity_of(loc, variant))
                        stat_g.append(loc.id)

                    # --- nowcaster: present conditions -> future severity ----
                    if horizon == 0:
                        continue
                    target_sev = severity_of(loc, truth_raw)
                    variants = [present_raw, drop_features(present_raw, rng, rng.randint(1, 2))]
                    for variant in variants:
                        norm = {k: normalise(k, v) for k, v in variant.items()}
                        now_X.append(build_vector(norm, horizon))
                        now_y.append(target_sev)
                        now_g.append(loc.id)

    return (
        {"X": np.asarray(stat_X), "y": np.asarray(stat_y), "groups": stat_g},
        {"X": np.asarray(now_X), "y": np.asarray(now_y), "groups": now_g},
    )


def split(ds: dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mask = np.asarray([g in HOLDOUT_LOCATIONS for g in ds["groups"]])
    return ds["X"][~mask], ds["y"][~mask], ds["X"][mask], ds["y"][mask]


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    err = y_pred - y_true
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
        "bias": round(float(err.mean()), 3),
        "p95_abs_error": round(float(np.percentile(np.abs(err), 95)), 3),
        "n": int(len(y_true)),
    }


def feature_names() -> List[str]:
    return (
        FEATURE_ORDER
        + ["horizon_fraction"]
        + [f"{f}__present" for f in FEATURE_ORDER]
    )


def save(path: str, model, meta: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump({"model": model, "meta": meta}, fh)
    print(f"  saved {path}  ({os.path.getsize(path) / 1024:.1f} KB)")


CAVEAT = (
    "Fitted on PEHRA's DETERMINISTIC SIMULATED scenarios. These figures measure "
    "agreement with the reference engine / the simulated future — they are NOT "
    "real-world forecasting accuracy and must never be presented as such."
)


def main() -> int:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    init_db()
    with session_scope() as db:
        seed_all(db)
        locations = db.query(Location).order_by(Location.id).all()
        locations = [db.merge(l) for l in locations]
        print(f"Locations: {len(locations)}  |  Scenarios: {len(SCENARIOS)}  |  "
              f"Horizons: {DEFAULT_HORIZONS_MIN}")
        print("Generating samples from the reference engine…")
        stat_ds, now_ds = build_datasets(locations)

    print(f"  statistical dataset: {stat_ds['X'].shape}")
    print(f"  nowcaster dataset:   {now_ds['X'].shape}")
    print(f"  held-out wards: {sorted(HOLDOUT_LOCATIONS)}")

    trained_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    names = feature_names()

    # ------------------------------------------------------------------
    print("\nFitting ridge regression (statistical)…")
    Xtr, ytr, Xte, yte = split(stat_ds)
    ridge = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=1.0))])
    ridge.fit(Xtr, ytr)
    train_m = metrics(ytr, ridge.predict(Xtr))
    test_m = metrics(yte, ridge.predict(Xte))
    print(f"  train {train_m}")
    print(f"  test  {test_m}")
    coefs = ridge.named_steps["ridge"].coef_
    importance = sorted(
        ({"feature": n, "weight": round(float(c), 4)} for n, c in zip(names, coefs)),
        key=lambda d: abs(d["weight"]), reverse=True,
    )[:15]
    save(os.path.join(ARTEFACT_DIR, "statistical.pkl"), ridge, {
        "version": "0.2",
        "algorithm": "Ridge(alpha=1.0) on standardised features",
        "trained_at": trained_at,
        "n_samples": int(stat_ds["X"].shape[0]),
        "n_features": int(stat_ds["X"].shape[1]),
        "target": "reference-engine compound severity index (0-100)",
        "split": {"kind": "grouped by location", "held_out": sorted(HOLDOUT_LOCATIONS)},
        "metrics": {"train": train_m, "holdout": test_m},
        "feature_importance": importance,
        "scenarios": sorted(SCENARIOS),
        "horizons_minutes": list(DEFAULT_HORIZONS_MIN),
        "caveat": CAVEAT,
    })

    # ------------------------------------------------------------------
    print("\nFitting gradient boosting (nowcaster)…")
    Xtr, ytr, Xte, yte = split(now_ds)
    gbr = GradientBoostingRegressor(
        n_estimators=280, learning_rate=0.07, max_depth=4,
        subsample=0.85, min_samples_leaf=12, random_state=20260908,
    )
    gbr.fit(Xtr, ytr)
    train_m = metrics(ytr, gbr.predict(Xtr))
    test_m = metrics(yte, gbr.predict(Xte))
    print(f"  train {train_m}")
    print(f"  test  {test_m}")
    importance = sorted(
        ({"feature": n, "importance": round(float(v), 4)}
         for n, v in zip(names, gbr.feature_importances_)),
        key=lambda d: d["importance"], reverse=True,
    )[:15]
    save(os.path.join(ARTEFACT_DIR, "nowcaster.pkl"), gbr, {
        "version": "0.3",
        "algorithm": "GradientBoostingRegressor(n=280, lr=0.07, depth=4, subsample=0.85)",
        "trained_at": trained_at,
        "n_samples": int(now_ds["X"].shape[0]),
        "n_features": int(now_ds["X"].shape[1]),
        "target": "severity index actually reached at the requested lead time",
        "inputs": "present conditions only — the forecast feed is deliberately withheld",
        "split": {"kind": "grouped by location", "held_out": sorted(HOLDOUT_LOCATIONS)},
        "metrics": {"train": train_m, "holdout": test_m},
        "feature_importance": importance,
        "scenarios": sorted(SCENARIOS),
        "horizons_minutes": [h for h in DEFAULT_HORIZONS_MIN if h > 0],
        "caveat": CAVEAT,
    })

    print("\nTop nowcaster features:")
    for row in importance[:8]:
        print(f"  {row['importance']:.4f}  {row['feature']}")
    print("\nDone. Restart the API so the registry reloads the artefacts.")
    print(json.dumps({"nowcaster_holdout": test_m}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
