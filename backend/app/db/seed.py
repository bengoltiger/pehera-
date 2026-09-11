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
# Locations -- Mumbai metropolitan core (island city + western/eastern suburbs)
# Elevation, slope and coastal exposure feed the DEM engine directly; low-lying
# reclaimed areas (BKC, Kurla, Mahim, Worli, Juhu) are the genuinely risky ones.
# ---------------------------------------------------------------------------
LOCATIONS = [
    dict(
        id="loc_colaba", name="Colaba Ward", name_hi="कुलाबा वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=18.9045, longitude=72.8111, elevation_m=6.5, slope_deg=1.5,
        coastal_exposure=0.92, area_km2=3.7,
        population=132000, vulnerable_population=26400, households=31000,
        terrain_vulnerability=0.62, drainage_deficiency=0.55, river_id=None,
        primary_hazards=["coastal_flood", "extreme_rain", "severe_wind", "urban_flood"],
    ),
    dict(
        id="loc_fort", name="Fort Ward", name_hi="फोर्ट वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=18.9350, longitude=72.8320, elevation_m=8.0, slope_deg=1.3,
        coastal_exposure=0.55, area_km2=2.2,
        population=93000, vulnerable_population=18600, households=22000,
        terrain_vulnerability=0.52, drainage_deficiency=0.45, river_id=None,
        primary_hazards=["coastal_flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_malabar_hill", name="Malabar Hill Ward", name_hi="मालाबार हिल वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=18.9480, longitude=72.7990, elevation_m=48.0, slope_deg=8.0,
        coastal_exposure=0.50, area_km2=2.5,
        population=68000, vulnerable_population=6800, households=18000,
        terrain_vulnerability=0.40, drainage_deficiency=0.30, river_id=None,
        primary_hazards=["severe_wind", "extreme_rain"],
    ),
    dict(
        id="loc_byculla", name="Byculla Ward", name_hi="बायकुला वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=18.9787, longitude=72.8343, elevation_m=6.0, slope_deg=1.0,
        coastal_exposure=0.05, area_km2=3.4,
        population=201000, vulnerable_population=44200, households=47000,
        terrain_vulnerability=0.68, drainage_deficiency=0.74, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_worli", name="Worli Ward", name_hi="वरळी वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=19.0160, longitude=72.8160, elevation_m=5.0, slope_deg=1.2,
        coastal_exposure=0.75, area_km2=4.6,
        population=154000, vulnerable_population=32300, households=36000,
        terrain_vulnerability=0.64, drainage_deficiency=0.78, river_id=None,
        primary_hazards=["coastal_flood", "urban_flood", "severe_wind", "extreme_rain"],
    ),
    dict(
        id="loc_dadar", name="Dadar Ward", name_hi="दादर वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=19.0210, longitude=72.8420, elevation_m=9.0, slope_deg=1.5,
        coastal_exposure=0.0, area_km2=3.9,
        population=187000, vulnerable_population=33600, households=44000,
        terrain_vulnerability=0.60, drainage_deficiency=0.60, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_parel", name="Parel Ward", name_hi="परळ वॉर्ड",
        admin_type="ward", district="Mumbai City", state="Maharashtra",
        latitude=19.0070, longitude=72.8400, elevation_m=5.5, slope_deg=0.9,
        coastal_exposure=0.0, area_km2=4.0,
        population=173000, vulnerable_population=38100, households=41000,
        terrain_vulnerability=0.66, drainage_deficiency=0.75, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_mahim", name="Mahim Ward", name_hi="माहिम वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0380, longitude=72.8440, elevation_m=4.5, slope_deg=0.8,
        coastal_exposure=0.75, area_km2=3.1,
        population=121000, vulnerable_population=29000, households=28000,
        terrain_vulnerability=0.70, drainage_deficiency=0.85, river_id=None,
        primary_hazards=["coastal_flood", "urban_flood", "flood", "severe_wind"],
    ),
    dict(
        id="loc_bandra", name="Bandra West Ward", name_hi="बांद्रा वेस्ट वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0596, longitude=72.8295, elevation_m=12.0, slope_deg=5.0,
        coastal_exposure=0.55, area_km2=3.6,
        population=148000, vulnerable_population=22200, households=36000,
        terrain_vulnerability=0.58, drainage_deficiency=0.50, river_id=None,
        primary_hazards=["coastal_flood", "severe_wind", "urban_flood"],
    ),
    dict(
        id="loc_bkc", name="Bandra–Kurla Complex Ward", name_hi="बांद्रा-कुर्ला कॉम्प्लेक्स वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0700, longitude=72.8650, elevation_m=3.0, slope_deg=0.5,
        coastal_exposure=0.35, area_km2=6.4,
        population=96000, vulnerable_population=21100, households=18000,
        terrain_vulnerability=0.72, drainage_deficiency=0.90, river_id="river_mithi",
        primary_hazards=["coastal_flood", "flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_sion", name="Sion Ward", name_hi="शीव वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0440, longitude=72.8620, elevation_m=11.0, slope_deg=2.2,
        coastal_exposure=0.0, area_km2=4.8,
        population=155000, vulnerable_population=32600, households=36000,
        terrain_vulnerability=0.59, drainage_deficiency=0.50, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_kurla", name="Kurla Ward", name_hi="कुर्ला वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0700, longitude=72.8800, elevation_m=4.0, slope_deg=0.7,
        coastal_exposure=0.15, area_km2=5.1,
        population=242000, vulnerable_population=72600, households=56000,
        terrain_vulnerability=0.76, drainage_deficiency=0.85, river_id="river_mithi",
        primary_hazards=["flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_chembur", name="Chembur Ward", name_hi="शेंबूर वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.0580, longitude=72.8960, elevation_m=13.0, slope_deg=2.5,
        coastal_exposure=0.10, area_km2=8.2,
        population=228000, vulnerable_population=47800, households=52000,
        terrain_vulnerability=0.57, drainage_deficiency=0.55, river_id=None,
        primary_hazards=["urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_vikhroli", name="Vikhroli Ward", name_hi="विक्रोळी वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1120, longitude=72.9300, elevation_m=7.0, slope_deg=1.2,
        coastal_exposure=0.35, area_km2=9.6,
        population=136000, vulnerable_population=29900, households=30000,
        terrain_vulnerability=0.61, drainage_deficiency=0.70, river_id=None,
        primary_hazards=["coastal_flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_andheri", name="Andheri East Ward", name_hi="अंधेरी पूर्व वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1196, longitude=72.8465, elevation_m=22.0, slope_deg=3.0,
        coastal_exposure=0.0, area_km2=10.4,
        population=311000, vulnerable_population=59000, households=71000,
        terrain_vulnerability=0.60, drainage_deficiency=0.45, river_id=None,
        primary_hazards=["urban_flood", "heat", "thunderstorm"],
    ),
    dict(
        id="loc_juhu", name="Juhu–Vile Parle Ward", name_hi="जुहू-विले पार्ले वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1070, longitude=72.8260, elevation_m=4.0, slope_deg=0.6,
        coastal_exposure=0.95, area_km2=5.3,
        population=98000, vulnerable_population=17600, households=24000,
        terrain_vulnerability=0.63, drainage_deficiency=0.55, river_id=None,
        primary_hazards=["coastal_flood", "severe_wind", "urban_flood", "flood"],
    ),
    dict(
        id="loc_powai", name="Powai Ward", name_hi="पवई वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1180, longitude=72.9070, elevation_m=33.0, slope_deg=6.0,
        coastal_exposure=0.05, area_km2=7.4,
        population=94000, vulnerable_population=9400, households=23000,
        terrain_vulnerability=0.45, drainage_deficiency=0.35, river_id="river_mithi",
        primary_hazards=["flood", "thunderstorm"],
    ),
    dict(
        id="loc_mulund", name="Mulund Ward", name_hi="मुलुंड वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1720, longitude=72.9570, elevation_m=7.5, slope_deg=1.4,
        coastal_exposure=0.30, area_km2=9.4,
        population=178000, vulnerable_population=32000, households=42000,
        terrain_vulnerability=0.55, drainage_deficiency=0.55, river_id=None,
        primary_hazards=["coastal_flood", "urban_flood", "extreme_rain"],
    ),
    dict(
        id="loc_borivali", name="Borivali Ward", name_hi="बोरिवली वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.2290, longitude=72.8550, elevation_m=19.0, slope_deg=4.0,
        coastal_exposure=0.05, area_km2=12.0,
        population=262000, vulnerable_population=47100, households=62000,
        terrain_vulnerability=0.50, drainage_deficiency=0.40, river_id="river_dahisar",
        primary_hazards=["flood", "heat", "extreme_rain"],
    ),
    dict(
        id="loc_goregaon", name="Goregaon Ward", name_hi="गोरेगाव वॉर्ड",
        admin_type="ward", district="Mumbai Suburban", state="Maharashtra",
        latitude=19.1650, longitude=72.8480, elevation_m=28.0, slope_deg=3.5,
        coastal_exposure=0.15, area_km2=11.2,
        population=224000, vulnerable_population=35800, households=53000,
        terrain_vulnerability=0.48, drainage_deficiency=0.40, river_id="river_oshawara",
        primary_hazards=["heat", "urban_flood", "thunderstorm"],
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
    ("hospital", "Neighbourhood Health Post", 0.95, 120, 0.004, 0.003),
    ("school", "Municipal School Building", 0.7, 450, -0.005, 0.004),
    ("shelter", "Municipal Relief Shelter", 0.85, 300, 0.003, -0.005),
    ("bridge", "Creek Crossing Bridge", 0.8, None, -0.003, -0.004),
    ("power", "Distribution Substation", 0.75, None, 0.005, 0.005),
]

EXTRA_INFRA = {
    "loc_fort": [("hospital", "St George Municipal Hospital", 0.9, 250, -0.004, -0.002),
                 ("shelter", "Cusrow Baug Open Ground Shelter", 0.8, 500, 0.004, 0.003)],
    "loc_byculla": [("hospital", "J. J. Group of Hospitals", 0.98, 800, -0.006, -0.002),
                    ("hospital", "Nair Municipal Hospital", 0.95, 550, 0.005, -0.004)],
    "loc_parel": [("hospital", "KEM Hospital, Parel", 0.99, 900, -0.004, 0.004)],
    "loc_malabar_hill": [("hospital", "Breach Candy Hospital", 0.97, 350, 0.003, 0.003)],
    "loc_worli": [("water", "Worli Sea-Face Drainage Outfall", 0.92, None, 0.004, -0.004)],
    "loc_sion": [("hospital", "Lokmanya Tilak General Hospital (Sion)", 0.97, 700, 0.003, -0.005)],
    "loc_bandra": [("hospital", "Lilavati Hospital", 0.98, 500, 0.005, -0.003),
                   ("bridge", "Bandra–Worli Sea Link Approach", 0.95, None, -0.005, 0.005)],
    "loc_mahim": [("hospital", "PD Hinduja National Hospital", 0.98, 600, -0.004, 0.004),
                  ("water", "Mithi Estuary Pumping Station", 0.9, None, 0.004, -0.002)],
    "loc_bkc": [("bridge", "Mithi River Bridge, BKC", 0.85, None, -0.003, -0.004),
                ("water", "BKC Storm Water Pumping Station", 0.92, None, 0.004, -0.004)],
    "loc_kurla": [("water", "Kurla Drainage Pumping Station", 0.9, None, 0.003, 0.004)],
    "loc_powai": [("hospital", "Fortis Hiranandani Hospital", 0.98, 400, 0.004, -0.004)],
    "loc_andheri": [("hospital", "Cooper Municipal Hospital", 0.95, 450, -0.004, 0.003),
                    ("hospital", "Nanavati Max Hospital, Vile Parle", 0.96, 500, 0.006, 0.002)],
    "loc_mulund": [("hospital", "Fortis Hospital, Mulund", 0.95, 500, -0.005, 0.002)],
    "loc_borivali": [("hospital", "Shatabdi Multispeciality Hospital", 0.93, 420, 0.002, -0.006)],
    "loc_goregaon": [("water", "Veer Savarkar Drainage Pumping Station", 0.88, None, -0.004, 0.004)],
}


# ---------------------------------------------------------------------------
# Historical incident archive (demo) -- Mumbai flood history
# ---------------------------------------------------------------------------
HISTORICAL_INCIDENTS = [
    dict(location_id="loc_kurla", hazard="flood", days_ago=7730,
         title="Mithi river overflow across Dharavi–Kurla (26 Jul 2005)", peak_risk=99.0,
         summary="944 mm of rain in 24 hours overwhelmed the Mithi; Dharavi and Kurla flooded up to 3 m, thousands relocated."),
    dict(location_id="loc_bkc", hazard="flood", days_ago=3302,
         title="Mithi embankment breach at BKC (29 Aug 2017)", peak_risk=92.0,
         summary="240 mm in a few hours plus a breached Mithi bank flooded the Bandra–Kurla Complex business district."),
    dict(location_id="loc_chembur", hazard="urban_flood", days_ago=3302,
         title="Chembur cloudburst waterlogging (29 Aug 2017)", peak_risk=90.0,
         summary="273 mm of rain in one tide window; drains overwhelmed, roads waterlogged for many hours."),
    dict(location_id="loc_sion", hazard="urban_flood", days_ago=1881,
         title="Low-lying Sion flash flood (14 Jul 2021)", peak_risk=87.0,
         summary="45-minute squall dumped over 40 mm; low-lying Sion lanes waterlogged knee-deep."),
    dict(location_id="loc_mahim", hazard="coastal_flood", days_ago=1570,
         title="High tide backed-up Mahim outfall (27 May 2022)", peak_risk=84.0,
         summary="Short intense burst at a spring high tide; drains could not discharge and Mahim causeway flooded."),
    dict(location_id="loc_fort", hazard="coastal_flood", days_ago=1568,
         title="Sea water surge near Gateway of India", peak_risk=78.0,
         summary="Onshore gale pushed sea water into the Fort esplanade during a storm swell."),
    dict(location_id="loc_juhu", hazard="coastal_flood", days_ago=769,
         title="Juhu beach road coastal inundation", peak_risk=80.0,
         summary="High tide combined with rough Arabian Sea swell overtopped the Juhu promenade."),
]

# demo users -- passwords come from a constant here ONLY because this is a
# prototype seed. Real deployments create users through the admin API.
SEED_USERS = [
    dict(username="citizen", full_name="Demo Citizen", role="citizen",
         password="citizen123", home_location_id="loc_colaba", language="en"),
    dict(username="nagrik", full_name="डेमो नागरिक", role="citizen",
         password="citizen123", home_location_id="loc_kurla", language="hi"),
    dict(username="authority", full_name="Demo Municipal Officer", role="authority",
         password="authority123", home_location_id=None, language="en",
         organisation="Brihanmumbai Municipal Corporation — Disaster Management Cell (demo)"),
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
                row.address = f"{area} municipal campus, Mumbai, Maharashtra {400001 + (h % 99)}"
                row.phone = f"+91 98200 {10000 + (h % 89999)}"

    # Backfill rows created before contact details existed (idempotent).
    for row in db.query(Infrastructure).filter(
        Infrastructure.kind.in_(["shelter", "hospital"]),
        Infrastructure.address.is_(None),
    ).all():
        area = (
            db.query(Location).filter(Location.id == row.location_id).first()
        )
        area_name = (area.name.split("–")[0].split(" Ward")[0]) if area else "Mumbai"
        h = int(hashlib.md5(row.id.encode()).hexdigest()[:8], 16)
        row.address = f"{area_name} municipal campus, Mumbai, Maharashtra {400001 + (h % 99)}"
        row.phone = f"+91 98200 {10000 + (h % 89999)}"
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
                id=1, scenario_id="mumbai_normal", tick=0, running=False, speed=1.0,
                overrides={}, connectivity="online", forced_failures={},
            )
        )

    db.commit()
    return created
