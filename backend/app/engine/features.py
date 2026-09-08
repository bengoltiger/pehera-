"""Feature assembly: provenance, freshness and data health (Sections 3, 13, 14).

This module turns provider output into the single validated feature bundle the
risk engine consumes. It is also where data honesty is enforced: nothing gets a
value without a source, a timestamp and a freshness verdict.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.risk_config import DATA_QUALITY_GRADES, FRESHNESS
from app.engine.normalise import ValidationIssue, label_for, normalise, validate_value
from app.providers.base import ObservationRecord, ProviderContext, ProviderError
from app.providers.registry import registry

FRESHNESS_LABELS = {
    "fresh": "Fresh",
    "aging": "Ageing",
    "stale": "Stale",
    "missing": "Unavailable",
}


def freshness_verdict(source_kind: str, age_seconds: float) -> str:
    prof = FRESHNESS.get(source_kind, FRESHNESS["default"])
    if age_seconds <= prof["fresh"]:
        return "fresh"
    if age_seconds <= prof["aging"]:
        return "aging"
    return "stale"


def human_age(age_seconds: float) -> str:
    s = int(max(0, age_seconds))
    if s < 60:
        return "just now" if s < 20 else f"{s} sec ago"
    m = s // 60
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    if h < 24:
        return f"{h} hr {m % 60} min ago"
    return f"{h // 24} d ago"


@dataclass
class FeatureValue:
    feature: str
    label: str
    value: Optional[float]
    unit: str
    source: str
    source_kind: str
    observed_at: Optional[dt.datetime]
    age_seconds: Optional[float]
    freshness: str
    quality: float
    is_simulated: bool
    observed_or_predicted: str
    normalised: Optional[float]
    unavailable_reason: Optional[str] = None
    validation_error: Optional[str] = None

    @property
    def usable(self) -> bool:
        return self.value is not None and self.freshness != "missing"

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "source_kind": self.source_kind,
            "observed_at": self.observed_at.isoformat() + "Z" if self.observed_at else None,
            "age_seconds": None if self.age_seconds is None else round(self.age_seconds),
            "age_human": human_age(self.age_seconds) if self.age_seconds is not None else "—",
            "freshness": self.freshness,
            "freshness_label": FRESHNESS_LABELS.get(self.freshness, self.freshness),
            "quality": round(self.quality, 3),
            "is_simulated": self.is_simulated,
            "observed_or_predicted": self.observed_or_predicted,
            "normalised": self.normalised,
            "unavailable_reason": self.unavailable_reason,
            "validation_error": self.validation_error,
        }


@dataclass
class ForecastValue:
    feature: str
    label: str
    value: Optional[float]
    unit: str
    horizon_minutes: int
    source: str
    model_agreement: float
    valid_at: dt.datetime
    is_simulated: bool

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "horizon_minutes": self.horizon_minutes,
            "source": self.source,
            "model_agreement": self.model_agreement,
            "valid_at": self.valid_at.isoformat() + "Z",
            "is_simulated": self.is_simulated,
            "observed_or_predicted": "predicted",
        }


@dataclass
class DataHealth:
    score: float
    grade: str
    by_source: List[dict]
    stale_features: List[str]
    missing_features: List[str]
    failed_providers: List[dict]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "grade": self.grade,
            "by_source": self.by_source,
            "stale_features": self.stale_features,
            "missing_features": self.missing_features,
            "failed_providers": self.failed_providers,
            "notes": self.notes,
        }


def _grade(score: float) -> str:
    for g in DATA_QUALITY_GRADES:
        if score >= g["min"]:
            return g["label"]
    return "Unusable"


@dataclass
class FeatureBundle:
    location_id: str
    now: dt.datetime
    features: Dict[str, FeatureValue]
    forecasts: List[ForecastValue]
    data_health: DataHealth
    connectivity: str
    scenario_id: str
    tick: int

    def value(self, feature: str) -> Optional[float]:
        fv = self.features.get(feature)
        return fv.value if fv and fv.usable else None

    def norm(self, feature: str) -> Optional[float]:
        fv = self.features.get(feature)
        if fv and fv.usable and fv.normalised is not None:
            return fv.normalised
        return None

    def raw_dict(self) -> Dict[str, Optional[float]]:
        return {k: (v.value if v.usable else None) for k, v in self.features.items()}

    def norm_dict(self) -> Dict[str, Optional[float]]:
        return {k: (v.normalised if v.usable else None) for k, v in self.features.items()}

    def metadata_dict(self) -> Dict[str, dict]:
        return {k: v.to_dict() for k, v in self.features.items()}

    def forecast_value(self, feature: str, horizon_minutes: int) -> Optional[float]:
        best = None
        for f in self.forecasts:
            if f.feature == feature and f.horizon_minutes == horizon_minutes:
                return f.value
            if f.feature == feature and (best is None or abs(f.horizon_minutes - horizon_minutes) < abs(best.horizon_minutes - horizon_minutes)):
                best = f
        return best.value if best else None

    def forecast_agreement(self) -> Optional[float]:
        vals = [f.model_agreement for f in self.forecasts if f.value is not None]
        return sum(vals) / len(vals) if vals else None


def assemble_features(location, ctx: ProviderContext) -> FeatureBundle:
    """Run every provider, validate, normalise, and score data health."""
    features: Dict[str, FeatureValue] = {}
    failed_providers: List[dict] = []
    by_source: List[dict] = []

    for provider in registry.all:
        records: List[ObservationRecord] = []
        error: Optional[str] = None
        try:
            records = provider.fetch(location, ctx)
        except ProviderError as exc:
            error = str(exc)
        except Exception as exc:  # never let one bad feed kill the pipeline
            error = f"Unexpected provider failure: {exc}"

        if error:
            failed_providers.append(
                {"provider": provider.display_name, "key": provider.key, "reason": error}
            )
            for feat in provider.features:
                features[feat] = FeatureValue(
                    feature=feat,
                    label=label_for(feat),
                    value=None,
                    unit="",
                    source=provider.display_name,
                    source_kind=provider.source_kind,
                    observed_at=None,
                    age_seconds=None,
                    freshness="missing",
                    quality=0.0,
                    is_simulated=provider.is_simulated,
                    observed_or_predicted="observed",
                    normalised=None,
                    unavailable_reason=error,
                )
            by_source.append(
                {
                    "source": provider.display_name,
                    "key": provider.key,
                    "kind": provider.source_kind,
                    "score": 0.0,
                    "grade": "Unusable",
                    "status": "unavailable",
                    "reason": error,
                    "is_simulated": provider.is_simulated,
                    "features": len(provider.features),
                    "age_human": "—",
                }
            )
            continue

        src_scores: List[float] = []
        oldest_age = 0.0
        for rec in records:
            validation_error = None
            value = rec.value
            try:
                value = validate_value(rec.feature, rec.value)
            except ValidationIssue as exc:
                validation_error = str(exc)
                value = None

            if value is None:
                fv = FeatureValue(
                    feature=rec.feature,
                    label=label_for(rec.feature),
                    value=None,
                    unit=rec.unit,
                    source=rec.source,
                    source_kind=rec.source_kind,
                    observed_at=rec.observed_at,
                    age_seconds=(ctx.now - rec.observed_at).total_seconds(),
                    freshness="missing",
                    quality=0.0,
                    is_simulated=rec.is_simulated,
                    observed_or_predicted=rec.observed_or_predicted,
                    normalised=None,
                    unavailable_reason=rec.unavailable_reason
                    or validation_error
                    or "Value not reported by the source",
                    validation_error=validation_error,
                )
                features[rec.feature] = fv
                src_scores.append(0.0)
                continue

            age = max(0.0, (ctx.now - rec.observed_at).total_seconds())
            verdict = freshness_verdict(rec.source_kind, age)
            oldest_age = max(oldest_age, age)
            fv = FeatureValue(
                feature=rec.feature,
                label=label_for(rec.feature),
                value=value,
                unit=rec.unit,
                source=rec.source,
                source_kind=rec.source_kind,
                observed_at=rec.observed_at,
                age_seconds=age,
                freshness=verdict,
                quality=rec.quality,
                is_simulated=rec.is_simulated,
                observed_or_predicted=rec.observed_or_predicted,
                normalised=normalise(rec.feature, value),
            )
            features[rec.feature] = fv
            fresh_factor = {"fresh": 1.0, "aging": 0.72, "stale": 0.35}[verdict]
            src_scores.append(100.0 * fresh_factor * max(0.0, min(1.0, rec.quality)))

        score = sum(src_scores) / len(src_scores) if src_scores else 0.0
        by_source.append(
            {
                "source": provider.display_name,
                "key": provider.key,
                "kind": provider.source_kind,
                "score": round(score, 1),
                "grade": _grade(score),
                "status": "operational" if score >= 55 else ("degraded" if score > 0 else "unavailable"),
                "reason": None,
                "is_simulated": provider.is_simulated,
                "features": len(records),
                "age_human": human_age(oldest_age),
            }
        )

    # ---- forecasts ----
    forecasts: List[ForecastValue] = []
    try:
        for fr in registry.forecast_provider.fetch_forecast(location, ctx):
            forecasts.append(
                ForecastValue(
                    feature=fr.feature,
                    label=label_for(fr.feature),
                    value=fr.value,
                    unit=fr.unit,
                    horizon_minutes=fr.horizon_minutes,
                    source=fr.source,
                    model_agreement=fr.model_agreement,
                    valid_at=fr.valid_at,
                    is_simulated=fr.is_simulated,
                )
            )
        fscore = 100.0 * (sum(f.model_agreement for f in forecasts) / len(forecasts)) if forecasts else 0.0
        by_source.append(
            {
                "source": "PEHRA Demo Nowcaster",
                "key": "forecast",
                "kind": "forecast",
                "score": round(fscore, 1),
                "grade": _grade(fscore),
                "status": "operational" if fscore >= 55 else "degraded",
                "reason": None,
                "is_simulated": True,
                "features": len(forecasts),
                "age_human": "just now",
            }
        )
    except ProviderError as exc:
        failed_providers.append({"provider": "PEHRA Demo Nowcaster", "key": "forecast", "reason": str(exc)})
        by_source.append(
            {
                "source": "PEHRA Demo Nowcaster",
                "key": "forecast",
                "kind": "forecast",
                "score": 0.0,
                "grade": "Unusable",
                "status": "unavailable",
                "reason": str(exc),
                "is_simulated": True,
                "features": 0,
                "age_human": "—",
            }
        )

    # Derive the headline forecast feature the flood models want.
    if "forecast_rain_3h" not in features:
        fr3 = None
        for f in forecasts:
            if f.feature == "forecast_rain_3h" and f.horizon_minutes == 0:
                fr3 = f
                break
        if fr3 and fr3.value is not None:
            features["forecast_rain_3h"] = FeatureValue(
                feature="forecast_rain_3h",
                label=label_for("forecast_rain_3h"),
                value=fr3.value,
                unit=fr3.unit,
                source=fr3.source,
                source_kind="forecast",
                observed_at=ctx.now,
                age_seconds=0.0,
                freshness="fresh",
                quality=fr3.model_agreement,
                is_simulated=True,
                observed_or_predicted="predicted",
                normalised=normalise("forecast_rain_3h", fr3.value),
            )
        else:
            features["forecast_rain_3h"] = FeatureValue(
                feature="forecast_rain_3h",
                label=label_for("forecast_rain_3h"),
                value=None,
                unit="mm",
                source="PEHRA Demo Nowcaster",
                source_kind="forecast",
                observed_at=None,
                age_seconds=None,
                freshness="missing",
                quality=0.0,
                is_simulated=True,
                observed_or_predicted="predicted",
                normalised=None,
                unavailable_reason="Forecast provider unavailable",
            )

    stale = sorted([f.feature for f in features.values() if f.freshness == "stale"])
    missing = sorted([f.feature for f in features.values() if not f.usable])
    scored = [s["score"] for s in by_source]
    overall = sum(scored) / len(scored) if scored else 0.0

    notes: List[str] = []
    if ctx.connectivity == "degraded":
        notes.append("Connection is degraded — feeds are arriving later than usual.")
        overall *= 0.85
    if ctx.connectivity == "offline":
        notes.append("Device is offline — showing the last cached state only.")
        overall = min(overall, 25.0)
    if stale:
        notes.append(f"{len(stale)} input(s) are stale and carry reduced weight in confidence.")
    if missing:
        notes.append(f"{len(missing)} input(s) are unavailable.")

    health = DataHealth(
        score=max(0.0, min(100.0, overall)),
        grade=_grade(overall),
        by_source=by_source,
        stale_features=stale,
        missing_features=missing,
        failed_providers=failed_providers,
        notes=notes,
    )

    return FeatureBundle(
        location_id=location.id,
        now=ctx.now,
        features=features,
        forecasts=forecasts,
        data_health=health,
        connectivity=ctx.connectivity,
        scenario_id=ctx.scenario_id,
        tick=ctx.tick,
    )
