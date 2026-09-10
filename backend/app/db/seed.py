"""Deterministic seed data (Section 89).

IMPORTANT: every record here is a FICTIONAL DEMO RECORD. Place names and
coordinates are real so the map is meaningful, but populations, terrain
indices, river associations, infrastructure and historical incidents are
invented for the prototype and are labelled `data_origin='demo_seed'`
throughout the API. Nothing here should be quoted as official data.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from sqlalchemy.orm import Session

from app.core.risk_config import HAZARDS
from app.db.models import (
    Hazard,
    Incident,
    Infrastructure,
    Location,
    ModelVersion,
    Scenario,
    SimulationState,
    User,
)
from app.security.passwords import hash_password
from app.simulation.scenarios import SCENARIOS

# ---------------------------------------------------------------------------
# Locations -- Pune district, Maharashtra
# ---------------------------------------------------------------------------
LOCATIONS = [
    dict(
        id="loc_sinhagad_road", name="Sinhagad Road Ward", name_hi="सिंहगड रोड वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.4575, longitude=73.8237, elevation_m=555.0, area_km2=8.4,
        population=142000, vulnerable_population=21300, households=32100,
        terrain_vulnerability=0.78, drainage_deficiency=0.62, river_id="river_mutha",
        primary_hazards=["flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_katraj", name="Katraj–Ambegaon Ward", name_hi="कात्रज–आंबेगाव वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.4483, longitude=73.8570, elevation_m=610.0, area_km2=7.1,
        population=118000, vulnerable_population=15300, households=27400,
        terrain_vulnerability=0.66, drainage_deficiency=0.81, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain", "thunderstorm"],
    ),
    dict(
        id="loc_hadapsar", name="Hadapsar–Mundhwa Ward", name_hi="हडपसर–मुंढवा वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.5089, longitude=73.9260, elevation_m=545.0, area_km2=10.5,
        population=187000, vulnerable_population=29900, households=42500,
        terrain_vulnerability=0.71, drainage_deficiency=0.74, river_id="river_mula_mutha",
        primary_hazards=["flood", "urban_flood"],
    ),
    dict(
        id="loc_baner", name="Baner–Balewadi Ward", name_hi="बाणेर–बालेवाडी वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.5590, longitude=73.7868, elevation_m=590.0, area_km2=9.2,
        population=96000, vulnerable_population=9600, households=24800,
        terrain_vulnerability=0.42, drainage_deficiency=0.48, river_id="river_mula",
        primary_hazards=["urban_flood", "thunderstorm"],
    ),
    dict(
        id="loc_pimpri", name="Pimpri Camp Ward", name_hi="पिंपरी कॅम्प वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.6280, longitude=73.8010, elevation_m=560.0, area_km2=6.8,
        population=165000, vulnerable_population=28100, households=38200,
        terrain_vulnerability=0.69, drainage_deficiency=0.77, river_id="river_pavana",
        primary_hazards=["flood", "urban_flood", "severe_wind"],
    ),
    dict(
        id="loc_chinchwad", name="Chinchwad Ward", name_hi="चिंचवड वॉर्ड",
        admin_type="ward", district="Pune", state="Maharashtra",
        latitude=18.6410, longitude=73.7930, elevation_m=570.0, area_km2=8.9,
        population=154000, vulnerable_population=20000, households=36000,
        terrain_vulnerability=0.55, drainage_deficiency=0.63, river_id="river_pavana",
        primary_hazards=["urban_flood", "severe_wind", "thunderstorm"],
    ),
    dict(
        id="loc_khadakwasla", name="Khadakwasla Village", name_hi="खडकवासला गाव",
        admin_type="village", district="Pune", state="Maharashtra",
        latitude=18.4404, longitude=73.7686, elevation_m=600.0, area_km2=5.5,
        population=6800, vulnerable_population=1500, households=1600,
        terrain_vulnerability=0.88, drainage_deficiency=0.45, river_id="river_mutha",
        primary_hazards=["flood", "extreme_rain"],
    ),
    dict(
        id="loc_mulshi", name="Mulshi Village", name_hi="मुळशी गाव",
        admin_type="village", district="Pune", state="Maharashtra",
        latitude=18.5100, longitude=73.5100, elevation_m=620.0, area_km2=12.0,
        population=4200, vulnerable_population=980, households=1050,
        terrain_vulnerability=0.74, drainage_deficiency=0.30, river_id="river_mula",
        primary_hazards=["flood", "extreme_rain"],
    ),
    dict(
        id="loc_velhe", name="Velhe Village", name_hi="वेल्हे गाव",
        admin_type="village", district="Pune", state="Maharashtra",
        latitude=18.3000, longitude=73.6300, elevation_m=730.0, area_km2=8.0,
        population=3100, vulnerable_population=760, households=780,
        terrain_vulnerability=0.81, drainage_deficiency=0.22, river_id=None,
        primary_hazards=["extreme_rain", "thunderstorm"],
    ),
    dict(
        id="loc_bhor", name="Bhor Town", name_hi="भोर शहर",
        admin_type="block", district="Pune", state="Maharashtra",
        latitude=18.1500, longitude=73.8430, elevation_m=620.0, area_km2=9.0,
        population=21000, vulnerable_population=4200, households=5100,
        terrain_vulnerability=0.63, drainage_deficiency=0.51, river_id="river_nira",
        primary_hazards=["flood", "extreme_rain"],
    ),
    dict(
        id="loc_junnar", name="Junnar Town", name_hi="जुन्नर शहर",
        admin_type="block", district="Pune", state="Maharashtra",
        latitude=19.2000, longitude=73.8750, elevation_m=680.0, area_km2=11.0,
        population=28000, vulnerable_population=5600, households=6800,
        terrain_vulnerability=0.58, drainage_deficiency=0.44, river_id="river_kukadi",
        primary_hazards=["flood", "thunderstorm", "severe_wind"],
    ),
    dict(
        id="loc_daund", name="Daund Town", name_hi="दौंड शहर",
        admin_type="block", district="Pune", state="Maharashtra",
        latitude=18.4640, longitude=74.5800, elevation_m=520.0, area_km2=14.0,
        population=68000, vulnerable_population=13600, households=15900,
        terrain_vulnerability=0.36, drainage_deficiency=0.40, river_id="river_bhima",
        primary_hazards=["heat", "flood", "severe_wind"],
    ),
]


def _square_polygon(lat: float, lng: float, area_km2: float):
    """Simple axis-aligned zone polygon derived from the recorded area.

    Real deployments would load actual ward boundaries; this is generated from
    data, never hardcoded per location (Section 58).
    """
    import math

    side_km = math.sqrt(max(area_km2, 0.25))
    dlat = (side_km / 2.0) / 110.574
    dlng = (side_km / 2.0) / (111.320 * math.cos(math.radians(lat)))
    return [
        [round(lat - dlat, 6), round(lng - dlng, 6)],
        [round(lat - dlat, 6), round(lng + dlng, 6)],
        [round(lat + dlat, 6), round(lng + dlng, 6)],
        [round(lat + dlat, 6), round(lng - dlng, 6)],
    ]


# ---------------------------------------------------------------------------
# Critical infrastructure (demo dataset)
# ---------------------------------------------------------------------------
INFRA_TEMPLATE = [
    ("hospital", "Community Health Centre", 0.95, 120, 0.004, 0.003),
    ("school", "Zilla Parishad School", 0.7, 450, -0.005, 0.004),
    ("shelter", "Municipal Relief Shelter", 0.85, 300, 0.003, -0.005),
    ("bridge", "River Crossing Bridge", 0.8, None, -0.003, -0.004),
    ("power", "Distribution Substation", 0.75, None, 0.005, 0.005),
]

EXTRA_INFRA = {
    "loc_sinhagad_road": [("hospital", "Sinhagad Road Multispeciality Hospital", 0.98, 240, 0.006, -0.002),
                          ("shelter", "Vitthalwadi Community Hall Shelter", 0.8, 400, -0.004, 0.006)],
    "loc_hadapsar": [("hospital", "Hadapsar General Hospital", 0.97, 300, -0.006, 0.002),
                     ("water", "Mundhwa Water Treatment Plant", 0.9, None, 0.004, 0.006)],
    "loc_pimpri": [("hospital", "Pimpri Civic Hospital", 0.96, 350, 0.005, 0.004),
                   ("shelter", "Camp Ground Relief Shelter", 0.82, 600, -0.005, -0.003)],
    "loc_khadakwasla": [("bridge", "Khadakwasla Causeway", 0.92, None, 0.002, 0.004)],
    "loc_daund": [("shelter", "Daund Rail Colony Shelter", 0.78, 250, 0.006, -0.006)],
}


# ---------------------------------------------------------------------------
# Historical incident archive (demo)
# ---------------------------------------------------------------------------
HISTORICAL_INCIDENTS = [
    dict(location_id="loc_sinhagad_road", hazard="flood", days_ago=412,
         title="Mutha overflow — Sinhagad Road low-lying stretch", peak_risk=88.0,
         summary="Sustained catchment rainfall with dam discharge; 1,900 residents temporarily relocated."),
    dict(location_id="loc_katraj", hazard="urban_flood", days_ago=298,
         title="Katraj cloudburst waterlogging", peak_risk=79.0,
         summary="68 mm in 90 minutes overwhelmed storm drains; underpass closed for 6 hours."),
    dict(location_id="loc_hadapsar", hazard="flood", days_ago=205,
         title="Mula-Mutha bank inundation at Mundhwa", peak_risk=83.0,
         summary="Riverside settlements flooded after upstream release."),
    dict(location_id="loc_pimpri", hazard="severe_wind", days_ago=156,
         title="Pre-monsoon squall, Pimpri Camp", peak_risk=72.0,
         summary="Gusts to 96 km/h; hoardings and 140 trees down."),
    dict(location_id="loc_khadakwasla", hazard="flood", days_ago=389,
         title="Khadakwasla causeway submersion", peak_risk=91.0,
         summary="Causeway submerged for 11 hours after high dam discharge."),
    dict(location_id="loc_daund", hazard="heat", days_ago=118,
         title="Daund heat episode", peak_risk=76.0,
         summary="Four consecutive days above 44 °C; cooling centres activated."),
    dict(location_id="loc_junnar", hazard="flood", days_ago=340,
         title="Kukadi tributary flash flood", peak_risk=81.0,
         summary="Rapid rise in a hill tributary after 120 mm in the upper catchment."),
]

# demo users -- passwords come from a constant here ONLY because this is a
# prototype seed. Real deployments create users through the admin API.
SEED_USERS = [
    dict(username="citizen", full_name="Demo Citizen", role="citizen",
         password="citizen123", home_location_id="loc_sinhagad_road", language="en"),
    dict(username="nagrik", full_name="डेमो नागरिक", role="citizen",
         password="citizen123", home_location_id="loc_katraj", language="hi"),
    dict(username="authority", full_name="Demo District Officer", role="authority",
         password="authority123", home_location_id=None, language="en",
         organisation="Pune District Disaster Management Authority (demo)"),
    dict(username="admin", full_name="Demo Administrator", role="administrator",
         password="admin12345", home_location_id=None, language="en",
         organisation="PEHRA System Administration (demo)"),
]


def seed_all(db: Session, *, force: bool = False) -> dict:
    """Idempotent seed. Returns a summary of what was created."""
    created = {"locations": 0, "infrastructure": 0, "users": 0, "hazards": 0,
               "scenarios": 0, "models": 0, "incidents": 0}

    # --- hazards ---
    for key, hz in HAZARDS.items():
        if not db.get(Hazard, key):
            db.add(Hazard(key=key, label=hz.label, icon=hz.icon, definition=hz.as_dict()))
            created["hazards"] += 1

    # --- locations ---
    for spec in LOCATIONS:
        existing = db.get(Location, spec["id"])
        if existing and not force:
            continue
        data = dict(spec)
        data["polygon"] = _square_polygon(spec["latitude"], spec["longitude"], spec["area_km2"])
        data["data_origin"] = "demo_seed"
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            db.add(Location(**data))
            created["locations"] += 1
    db.flush()

    # --- infrastructure ---
    for spec in LOCATIONS:
        items = list(INFRA_TEMPLATE) + EXTRA_INFRA.get(spec["id"], [])
        for i, (kind, name, crit, cap, dlat, dlng) in enumerate(items):
            iid = f"inf_{spec['id'][4:]}_{i}"
            area = spec["name"].split("–")[0].split(" Ward")[0]
            row = db.get(Infrastructure, iid)
            if row is None:
                row = Infrastructure(
                    id=iid,
                    location_id=spec["id"],
                    name=f"{name}, {area}",
                    kind=kind,
                    latitude=round(spec["latitude"] + dlat, 6),
                    longitude=round(spec["longitude"] + dlng, 6),
                    capacity=cap,
                    criticality=crit,
                    data_origin="demo_seed",
                )
                db.add(row)
                created["infrastructure"] += 1
            # Contact details for places a citizen would actually call or walk
            # to. Deterministic per row so re-seeding never changes them.
            if kind in ("shelter", "hospital") and not row.address:
                h = int(hashlib.md5(iid.encode()).hexdigest()[:8], 16)
                row.address = f"{area} municipal campus, Pune, Maharashtra {411001 + (h % 99)}"
                row.phone = f"+91 98220 {10000 + (h % 89999)}"

    # Backfill rows created before contact details existed (idempotent).
    for row in db.query(Infrastructure).filter(
        Infrastructure.kind.in_(["shelter", "hospital"]),
        Infrastructure.address.is_(None),
    ).all():
        area = (
            db.query(Location).filter(Location.id == row.location_id).first()
        )
        area_name = (area.name.split("–")[0].split(" Ward")[0]) if area else "Pune"
        h = int(hashlib.md5(row.id.encode()).hexdigest()[:8], 16)
        row.address = f"{area_name} municipal campus, Pune, Maharashtra {411001 + (h % 99)}"
        row.phone = f"+91 98220 {10000 + (h % 89999)}"
        created["infrastructure"] += 1

    # --- users ---
    for u in SEED_USERS:
        if db.query(User).filter(User.username == u["username"]).first():
            continue
        db.add(
            User(
                username=u["username"],
                full_name=u["full_name"],
                password_hash=hash_password(u["password"]),
                role=u["role"],
                organisation=u.get("organisation"),
                home_location_id=u.get("home_location_id"),
                language=u.get("language", "en"),
            )
        )
        created["users"] += 1

    # --- scenarios ---
    for sid, s in SCENARIOS.items():
        if db.get(Scenario, sid):
            continue
        db.add(
            Scenario(
                id=sid,
                name=s.name,
                description=s.description,
                hazard_focus=s.hazard_focus,
                focus_location_id=s.focus_location_id,
                tick_minutes=s.tick_minutes,
                total_ticks=s.total_ticks,
                definition=s.as_dict(),
                is_deterministic=True,
            )
        )
        created["scenarios"] += 1

    # --- model versions ---
    from app.riskmodels.registry import model_registry

    for m in model_registry.all():
        mid = f"mdl_{m.kind}_{m.version.replace('.', '_')}"
        if db.get(ModelVersion, mid):
            continue
        db.add(
            ModelVersion(
                id=mid,
                name=m.name,
                version=m.version,
                kind=m.kind,
                description=m.description,
                is_active=(m.kind == model_registry.preferred),
                trained_on=m.trained_on,
                measured_metrics=None,  # never fabricated; filled by verification
            )
        )
        created["models"] += 1

    # --- historical incident archive ---
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for h in HISTORICAL_INCIDENTS:
        iid = f"inc_hist_{h['location_id'][4:]}_{h['days_ago']}"
        if db.get(Incident, iid):
            continue
        detected = now - dt.timedelta(days=h["days_ago"])
        db.add(
            Incident(
                id=iid,
                location_id=h["location_id"],
                hazard=h["hazard"],
                title=h["title"],
                status="archived",
                peak_risk=h["peak_risk"],
                peak_at=detected + dt.timedelta(hours=3),
                detected_at=detected,
                first_warning_at=detected + dt.timedelta(minutes=75),
                resolved_at=detected + dt.timedelta(hours=9),
                lead_time_seconds=int(3 * 3600 - 75 * 60),
                story=[
                    {
                        "at": (detected + dt.timedelta(minutes=0)).isoformat() + "Z",
                        "text": h["summary"],
                        "kind": "archive",
                    }
                ],
                timeline=[{"stage": "Archived record", "at": detected.isoformat() + "Z"}],
                scenario_id=None,
            )
        )
        created["incidents"] += 1

    # --- simulation state singleton ---
    state = db.get(SimulationState, 1)
    if not state:
        db.add(
            SimulationState(
                id=1, scenario_id="normal_day", tick=0, running=False, speed=1.0,
                overrides={}, connectivity="online", forced_failures={},
            )
        )

    db.commit()
    return created
