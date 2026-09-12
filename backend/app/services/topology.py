"""Mumbai regional topology bundle (Predict / Telemetry map).

The Predict screen used to paint a cartoon circular radar; the authority asked
for something closer to their mental model of Mumbai instead. This module
serves an **indicative** overview of the region: wards, rivers, creeks, lakes,
mangroves, salt pans, forests, chronic flood spots and the transport skeleton.

Honesty rule: these polygons are hand-drawn approximations for a live demo —
they are deliberately *not* survey-accurate (no ward boundary file, no verified
DEM), and every consumer is expected to render that label. Coordinates are
[lat, lng], matching the rest of the API.
"""
from __future__ import annotations

from app.services.clock import utcnow  # reuse the app's clock for generated_at

_REGION = {
    "name": "Mumbai Metropolitan Region",
    "short_name": "Mumbai",
    "center": [19.11, 72.86],
    "km_bounds": [18.90, 72.76, 19.31, 73.02],  # [lat_min, lng_min, lat_max, lng_max]
    "zoom": 11,
    "zone_count": 24,
}

_CATEGORIES: list[dict] = [
    {"id": "admin", "label": "Administration", "color": "#64748b"},
    {"id": "hydro", "label": "Hydrography", "color": "#38bdf8"},
    {"id": "ecology", "label": "Ecology", "color": "#34d399"},
    {"id": "risk", "label": "Flood risk", "color": "#ef4444"},
    {"id": "transport", "label": "Transport", "color": "#f5b942"},
]

_LAYERS: list[dict] = [
    # ------------------------------------------------------------ admin --
    {
        "id": "wards",
        "category": "admin",
        "kind": "point",
        "name": "MCGM Wards (24)",
        "summary": "Administrative wards of Greater Mumbai, spot-placed (indicative centroids).",
        "features": [
            {"name": "Ward A — Colaba / Fort", "lat": 18.928, "lng": 72.832},
            {"name": "Ward B — Mandvi / Masjid", "lat": 18.952, "lng": 72.838},
            {"name": "Ward C — Marine Lines / Fort", "lat": 18.943, "lng": 72.826},
            {"name": "Ward D — Tardeo / Grant Road", "lat": 18.956, "lng": 72.808},
            {"name": "Ward E — Byculla / Chief", "lat": 18.978, "lng": 72.832},
            {"name": "Ward F/N — Matunga / Sion", "lat": 19.028, "lng": 72.855},
            {"name": "Ward F/S — Parel / Elphinstone", "lat": 19.006, "lng": 72.845},
            {"name": "Ward G/N — Dadar / Mahim", "lat": 19.034, "lng": 72.843},
            {"name": "Ward G/S — Worli / Prabhadevi", "lat": 19.008, "lng": 72.820},
            {"name": "Ward H/E — Bandra East / Khar East", "lat": 19.062, "lng": 72.852},
            {"name": "Ward H/W — Santacruz / Bandra West", "lat": 19.078, "lng": 72.827},
            {"name": "Ward K/E — Andheri East / Vile Parle", "lat": 19.113, "lng": 72.872},
            {"name": "Ward K/W — Andheri West / Juhu", "lat": 19.122, "lng": 72.828},
            {"name": "Ward L — Kurla / Sion West", "lat": 19.068, "lng": 72.879},
            {"name": "Ward M/E — Chembur / Deonar", "lat": 19.048, "lng": 72.911},
            {"name": "Ward M/W — Elphinstone / Dadar West", "lat": 18.999, "lng": 72.838},
            {"name": "Ward N — Borivali / Dahisar", "lat": 19.231, "lng": 72.847},
            {"name": "Ward P/N — Kandivali / Charkop", "lat": 19.202, "lng": 72.859},
            {"name": "Ward P/S — Goregaon / Aarey", "lat": 19.157, "lng": 72.847},
            {"name": "Ward R/N — Jogeshwari East", "lat": 19.101, "lng": 72.859},
            {"name": "Ward R/C — Dadar West / Matunga", "lat": 19.017, "lng": 72.848},
            {"name": "Ward R/S — Worli seaface", "lat": 19.005, "lng": 72.817},
            {"name": "Ward S — Bhandup / Mulund / Vikhroli", "lat": 19.113, "lng": 72.930},
            {"name": "Ward T — Kurla / Ghatkopar West", "lat": 19.078, "lng": 72.895},
        ],
    },
    {
        "id": "districts",
        "category": "admin",
        "kind": "polygon",
        "name": "Districts (coarse)",
        "summary": "Rough extent of Mumbai City and Mumbai Suburban districts.",
        "features": [
            {
                "name": "Mumbai City district (island)",
                "coords": [
                    [18.900, 72.795], [18.910, 72.800], [18.925, 72.790], [18.935, 72.805],
                    [18.935, 72.820], [18.930, 72.830], [18.940, 72.840], [18.955, 72.845],
                    [18.975, 72.845], [18.995, 72.855], [19.010, 72.850], [19.020, 72.860],
                    [19.035, 72.855], [19.040, 72.865], [19.025, 72.885], [19.000, 72.900],
                    [18.970, 72.900], [18.940, 72.885], [18.915, 72.870], [18.900, 72.850],
                    [18.900, 72.820],
                ],
            },
            {
                "name": "Mumbai Suburban district",
                "coords": [
                    [19.025, 72.898], [19.050, 72.900], [19.100, 72.930], [19.150, 72.940],
                    [19.200, 72.960], [19.250, 72.940], [19.300, 72.900], [19.290, 72.820],
                    [19.250, 72.800], [19.200, 72.790], [19.150, 72.800], [19.100, 72.810],
                    [19.060, 72.820], [19.040, 72.825], [19.030, 72.845], [19.020, 72.862],
                    [19.025, 72.880],
                ],
            },
        ],
    },
    # ----------------------------------------------------------- hydro -- 
    {
        "id": "rivers",
        "category": "hydro",
        "kind": "polyline",
        "name": "Rivers",
        "summary": "Mithi (through BKC), Dahisar, Poisar and Oshiwara — the monsoon flood carriers.",
        "features": [
            {
                "name": "Mithi River (18 km)",
                "detail": "Vihar + Powai overflows → Marol → Kurla → BKC → Dharavi → Mahim Creek",
                "coords": [
                    [19.090, 72.906], [19.100, 72.900], [19.120, 72.900], [19.132, 72.910],
                    [19.135, 72.895], [19.125, 72.888], [19.110, 72.880], [19.095, 72.880],
                    [19.085, 72.882], [19.075, 72.881], [19.070, 72.875], [19.075, 72.868],
                    [19.065, 72.862], [19.055, 72.852], [19.046, 72.847], [19.040, 72.842],
                ],
            },
            {
                "name": "Dahisar River",
                "detail": "Tulsi Lake outflow → Dahisar → Marve / Gorai mouth",
                "coords": [
                    [19.176, 72.903], [19.190, 72.880], [19.210, 72.865], [19.225, 72.855],
                    [19.238, 72.845], [19.240, 72.830], [19.230, 72.815], [19.205, 72.790],
                    [19.200, 72.780],
                ],
            },
            {
                "name": "Poisar River",
                "detail": "SGNP western edge → Malad Creek",
                "coords": [
                    [19.175, 72.885], [19.160, 72.870], [19.145, 72.855], [19.130, 72.840],
                    [19.120, 72.830], [19.115, 72.825],
                ],
            },
            {
                "name": "Oshiwara River",
                "detail": "Aarey → Versova / Malad Creek",
                "coords": [
                    [19.140, 72.875], [19.130, 72.860], [19.120, 72.850], [19.110, 72.840],
                    [19.100, 72.822],
                ],
            },
        ],
    },
    {
        "id": "creeks",
        "category": "hydro",
        "kind": "polyline",
        "name": "Creeks & coastline",
        "summary": "Mahim, Thane, Vasai and Malad creeks — tidal arms that flood behind the sea wall.",
        "features": [
            {
                "name": "Mahim Creek",
                "coords": [
                    [19.045, 72.842], [19.050, 72.860], [19.040, 72.875],
                    [19.025, 72.890], [19.020, 72.900],
                ],
            },
            {
                "name": "Thane Creek",
                "coords": [
                    [19.260, 72.980], [19.200, 72.960], [19.140, 72.940], [19.060, 72.930],
                    [18.990, 72.920], [18.940, 72.900], [18.900, 72.870],
                ],
            },
            {
                "name": "Vasai Creek / Bhayandar",
                "coords": [[19.300, 72.830], [19.280, 72.790], [19.240, 72.775]],
            },
            {
                "name": "Malad Creek (Versova–Marve arm)",
                "coords": [
                    [19.145, 72.790], [19.130, 72.795], [19.115, 72.815], [19.100, 72.820],
                ],
            },
            {
                "name": "Gorai–Manori channel",
                "coords": [[19.215, 72.775], [19.205, 72.792], [19.190, 72.800]],
            },
        ],
    },
    {
        "id": "lakes",
        "category": "hydro",
        "kind": "polygon",
        "name": "Lakes (drinking + overflow risk)",
        "summary": "The three reservoirs that sit upstream of Mithi routing.",
        "features": [
            {
                "name": "Tulsi Lake",
                "coords": [
                    [19.170, 72.894], [19.185, 72.894], [19.185, 72.905],
                    [19.170, 72.905], [19.170, 72.894],
                ],
            },
            {
                "name": "Vihar Lake",
                "coords": [
                    [19.082, 72.898], [19.098, 72.898], [19.098, 72.914],
                    [19.082, 72.914], [19.082, 72.898],
                ],
            },
            {
                "name": "Powai Lake",
                "coords": [
                    [19.115, 72.902], [19.130, 72.902], [19.132, 72.918],
                    [19.116, 72.918], [19.115, 72.902],
                ],
            },
        ],
    },
    {
        "id": "salt_pans",
        "category": "hydro",
        "kind": "polygon",
        "name": "Salt pans (low-lying)",
        "summary": "The city's natural stormwater sponges — and its most flood-prone flats.",
        "features": [
            {
                "name": "Sewri–Mahul salt pan",
                "coords": [
                    [19.035, 72.890], [19.045, 72.905], [19.025, 72.925],
                    [19.005, 72.915], [19.005, 72.895], [19.015, 72.885],
                ],
            },
            {
                "name": "Mahim salt pan",
                "coords": [
                    [19.040, 72.850], [19.050, 72.860], [19.045, 72.875],
                    [19.030, 72.870], [19.030, 72.855],
                ],
            },
            {
                "name": "Manori / Gorai salt pan",
                "coords": [
                    [19.215, 72.790], [19.225, 72.800], [19.210, 72.820],
                    [19.190, 72.810], [19.190, 72.795],
                ],
            },
            {
                "name": "Khardanda / Versova salt pan",
                "coords": [
                    [19.120, 72.805], [19.130, 72.815], [19.120, 72.825],
                    [19.105, 72.820], [19.105, 72.810],
                ],
            },
        ],
    },
    # ---------------------------------------------------------- ecology --
    {
        "id": "sgnp",
        "category": "ecology",
        "kind": "polygon",
        "name": "Sanjay Gandhi NP",
        "summary": "647 km² protected forest — its streams feed Poisar and Mithi.",
        "features": [
            {
                "name": "SGNP (Borivali)",
                "coords": [
                    [19.140, 72.855], [19.150, 72.875], [19.170, 72.885], [19.190, 72.885],
                    [19.210, 72.875], [19.225, 72.885], [19.235, 72.870], [19.230, 72.850],
                    [19.210, 72.840], [19.190, 72.840], [19.160, 72.845],
                ],
            },
        ],
    },
    {
        "id": "mangroves",
        "category": "ecology",
        "kind": "polygon",
        "name": "Mangroves",
        "summary": "Creek fringes — first defence against tidal surge, regularly eroded.",
        "features": [
            {
                "name": "Mahim–BKC mangrove belt",
                "coords": [
                    [19.050, 72.845], [19.045, 72.852], [19.025, 72.852], [19.025, 72.845],
                ],
            },
            {
                "name": "Sewri mangroves",
                "coords": [
                    [19.005, 72.895], [19.010, 72.905], [18.990, 72.905], [18.990, 72.895],
                ],
            },
            {
                "name": "Thane Creek mangroves",
                "coords": [
                    [19.160, 72.955], [19.170, 72.965], [19.080, 72.955],
                    [19.020, 72.940], [19.005, 72.925],
                ],
            },
            {
                "name": "Dahisar delta mangroves",
                "coords": [
                    [19.210, 72.790], [19.220, 72.800], [19.205, 72.810], [19.195, 72.800],
                ],
            },
        ],
    },
    # ------------------------------------------------------------- risk --
    {
        "id": "flood_hotspots",
        "category": "risk",
        "kind": "point",
        "name": "Chronic flood spots",
        "summary": "Recurring Mumbaikar landmarks — every rainy season makes the news.",
        "features": [
            {"name": "Hindmata Cinema", "lat": 19.0128, "lng": 72.8485, "detail": "Chronic waterlogging"},
            {"name": "King's Circle", "lat": 19.030, "lng": 72.858, "detail": "Chronic waterlogging"},
            {"name": "Matunga", "lat": 19.025, "lng": 72.853, "detail": "Chronic waterlogging"},
            {"name": "Dadar TT", "lat": 19.021, "lng": 72.842, "detail": "Chronic waterlogging"},
            {"name": "Sion", "lat": 19.040, "lng": 72.860, "detail": "Subway + rail underpass"},
            {"name": "Khar subway", "lat": 19.073, "lng": 72.841, "detail": "Subway floods fast"},
            {"name": "Vakola", "lat": 19.077, "lng": 72.847, "detail": "Chronic waterlogging"},
            {"name": "Milan subway", "lat": 19.101, "lng": 72.855, "detail": "Subway floods fast"},
            {"name": "Andheri subway", "lat": 19.119, "lng": 72.846, "detail": "Subway floods fast"},
            {"name": "JVLR", "lat": 19.103, "lng": 72.872, "detail": "Chronic waterlogging"},
            {"name": "BKC", "lat": 19.074, "lng": 72.868, "detail": "Mithi overflow plain"},
            {"name": "Kurla", "lat": 19.069, "lng": 72.880, "detail": "Low-lying, drains back up"},
            {"name": "Sakinaka", "lat": 19.095, "lng": 72.875, "detail": "Chronic waterlogging"},
            {"name": "Chunabhatti", "lat": 19.050, "lng": 72.868, "detail": "Tidal creek backflow"},
            {"name": "Chembur", "lat": 19.020, "lng": 72.895, "detail": "Chronic waterlogging"},
            {"name": "Sewri", "lat": 18.988, "lng": 72.870, "detail": "Tidal low ground"},
            {"name": "Mahul", "lat": 19.017, "lng": 72.892, "detail": "Refinery low ground"},
            {"name": "Marol", "lat": 19.110, "lng": 72.878, "detail": "Chronic waterlogging"},
            {"name": "Kanjurmarg", "lat": 19.128, "lng": 72.931, "detail": "Chronic waterlogging"},
            {"name": "Bhandup", "lat": 19.143, "lng": 72.934, "detail": "Chronic waterlogging"},
            {"name": "Mulund", "lat": 19.169, "lng": 72.949, "detail": "Chronic waterlogging"},
            {"name": "Malad", "lat": 19.155, "lng": 72.847, "detail": "Chronic waterlogging"},
            {"name": "Kandivali", "lat": 19.199, "lng": 72.870, "detail": "Chronic waterlogging"},
            {"name": "Borivali", "lat": 19.231, "lng": 72.849, "detail": "Chronic waterlogging"},
            {"name": "Dahisar", "lat": 19.241, "lng": 72.848, "detail": "Riverine overflow"},
            {"name": "Worli seaface", "lat": 19.005, "lng": 72.817, "detail": "Wave overtopping"},
            {"name": "Gateway low-lying", "lat": 18.921, "lng": 72.835, "detail": "High-tide flooding"},
            {"name": "Cuffe Parade", "lat": 18.903, "lng": 72.803, "detail": "Reclaimed low ground"},
        ],
    },
    {
        "id": "reclamation",
        "category": "risk",
        "kind": "polygon",
        "name": "Reclaimed / low-lying",
        "summary": "Land that was water — breathes the sea back in on a bad tide.",
        "features": [
            {
                "name": "South Mumbai reclamation (Nariman Pt–Cuffe Parade)",
                "coords": [
                    [18.905, 72.800], [18.915, 72.800], [18.935, 72.815],
                    [18.940, 72.828], [18.930, 72.835], [18.915, 72.830], [18.905, 72.815],
                ],
            },
            {
                "name": "BKC + eastern Dharavi",
                "coords": [
                    [19.062, 72.865], [19.082, 72.875], [19.075, 72.885], [19.055, 72.875],
                ],
            },
            {
                "name": "Kanjurmarg East",
                "coords": [
                    [19.110, 72.920], [19.140, 72.940], [19.130, 72.950], [19.100, 72.930],
                ],
            },
            {
                "name": "Sewri–Mahul belt",
                "coords": [
                    [18.995, 72.885], [19.020, 72.895], [19.030, 72.910],
                    [19.000, 72.915], [18.990, 72.900],
                ],
            },
        ],
    },
    # -------------------------------------------------------- transport --
    {
        "id": "rail",
        "category": "transport",
        "kind": "polyline",
        "name": "Rail — Western, Central, Harbour",
        "summary": "The suburban backbone the city tunnels and bridges around.",
        "features": [
            {
                "name": "Western line (Churchgate → Dahisar)",
                "coords": [
                    [18.934, 72.828], [18.943, 72.822], [18.952, 72.819], [18.958, 72.818],
                    [18.968, 72.820], [18.980, 72.814], [18.993, 72.822], [19.016, 72.844],
                    [19.030, 72.847], [19.044, 72.849], [19.060, 72.837], [19.078, 72.833],
                    [19.098, 72.839], [19.118, 72.844], [19.139, 72.840], [19.158, 72.845],
                    [19.178, 72.848], [19.199, 72.856], [19.218, 72.855], [19.231, 72.842],
                    [19.243, 72.843],
                ],
            },
            {
                "name": "Central line (CST → Mulund)",
                "coords": [
                    [18.940, 72.835], [18.976, 72.832], [19.017, 72.845], [19.072, 72.876],
                    [19.086, 72.897], [19.110, 72.918], [19.146, 72.933], [19.172, 72.947],
                ],
            },
            {
                "name": "Harbour line (CST → Govandi)",
                "coords": [
                    [18.940, 72.835], [19.020, 72.855], [19.070, 72.872],
                    [19.055, 72.898], [19.040, 72.925],
                ],
            },
        ],
    },
    {
        "id": "metro",
        "category": "transport",
        "kind": "polyline",
        "name": "Metro (1, 2A, 3, 7)",
        "summary": "Current and under-construction corridors.",
        "features": [
            {
                "name": "Metro Line 1 — Versova → Ghatkopar",
                "coords": [
                    [19.117, 72.830], [19.112, 72.842], [19.102, 72.853], [19.092, 72.867],
                    [19.098, 72.875], [19.101, 72.888], [19.102, 72.902], [19.091, 72.912],
                ],
            },
            {
                "name": "Metro Line 2A — Dahisar East → DN Nagar",
                "coords": [
                    [19.243, 72.851], [19.216, 72.858], [19.190, 72.856], [19.162, 72.850],
                    [19.140, 72.842], [19.120, 72.840], [19.112, 72.842],
                ],
            },
            {
                "name": "Metro Line 3 — Colaba → Aarey (Aqua)",
                "coords": [
                    [18.906, 72.800], [18.920, 72.826], [18.940, 72.828], [18.968, 72.822],
                    [19.000, 72.832], [19.020, 72.843], [19.040, 72.849], [19.060, 72.838],
                    [19.078, 72.855], [19.098, 72.860], [19.120, 72.852], [19.140, 72.853],
                    [19.155, 72.858],
                ],
            },
            {
                "name": "Metro Line 7 — Dahisar East → Andheri East",
                "coords": [
                    [19.243, 72.851], [19.202, 72.875], [19.168, 72.878],
                    [19.140, 72.880], [19.115, 72.878],
                ],
            },
        ],
    },
    {
        "id": "roads",
        "category": "transport",
        "kind": "polyline",
        "name": "Key roads & links",
        "summary": "Emergency lifelines that congest first in the rain.",
        "features": [
            {
                "name": "Western Express Highway",
                "coords": [
                    [19.055, 72.843], [19.080, 72.846], [19.100, 72.852], [19.120, 72.852],
                    [19.140, 72.850], [19.160, 72.852], [19.180, 72.858], [19.200, 72.866],
                    [19.220, 72.865], [19.240, 72.856],
                ],
            },
            {
                "name": "Eastern Express Highway",
                "coords": [
                    [19.020, 72.862], [19.045, 72.882], [19.070, 72.903],
                    [19.100, 72.925], [19.130, 72.933], [19.155, 72.935], [19.175, 72.955],
                ],
            },
            {
                "name": "JVLR (Jogeshwari–Vikhroli Link Rd)",
                "coords": [
                    [19.141, 72.846], [19.132, 72.861], [19.120, 72.879],
                    [19.114, 72.898], [19.108, 72.916],
                ],
            },
            {
                "name": "LBS Marg",
                "coords": [
                    [19.055, 72.868], [19.070, 72.887], [19.088, 72.903], [19.110, 72.922],
                ],
            },
            {
                "name": "Sion–Panvel Expressway (SE corridor)",
                "coords": [
                    [19.032, 72.856], [19.045, 72.878], [19.050, 72.897], [19.040, 72.925],
                ],
            },
            {
                "name": "Bandra–Worli Sea Link",
                "coords": [[19.056, 72.822], [19.035, 72.820], [19.016, 72.818]],
            },
            {
                "name": "Coastal Road (under construction)",
                "detail": "Marine Drive–Worli–Bandra extension",
                "coords": [
                    [18.928, 72.825], [18.950, 72.817], [18.975, 72.800],
                    [19.000, 72.795], [19.030, 72.795], [19.056, 72.805],
                ],
            },
        ],
    },
]


def build_topology() -> dict:
    """Bundle the static Mumbai topology for /api/map/topology."""
    return {
        "region": _REGION,
        "categories": _CATEGORIES,
        "layers": _LAYERS,
        "layer_count": len(_LAYERS),
        "generated_at": utcnow().isoformat(timespec="seconds"),
        "is_simulated": True,
        "note": (
            "Indicative weekend-demo geometry: ward centroids, river chains and "
            "polygons are hand-drawn approximations, NOT survey-accurate. Use "
            "for situational orientation, never for engineering decisions."
        ),
    }