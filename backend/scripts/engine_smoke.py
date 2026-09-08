from app.db.session import init_db, SessionLocal
from app.db.seed import seed_all
from app.services.orchestrator import refresh_region, step, set_scenario, reset_demo, replay_scenario, verify_predictions, what_if
from app.db.models import Location, Alert
init_db(); db=SessionLocal(); seed_all(db)
reset_demo(db, scenario_id="river_flood")
out = refresh_region(db)
print("cells:", len(out["summary"]["threat_cells"]))
for i in range(0, 14):
    r = step(db, steps=1)
s = r["last"]
print("tick", r["tick"], "cells", len(s["threat_cells"]))
for c in s["threat_cells"]:
    print("  cell", c["hazard"], c["severity_label"], "sev", c["current_severity"], "move", c["movement"]["speed_kmh"], c["movement"]["compass"], "track", len(c["track"]))
print("PRIORITY QUEUE top3:")
for q in s["priority_queue"][:3]:
    print(f"  #{q['rank']} {q['location_name']:24s} risk={q['risk']:.0f} exp={q['exposed_population']:,} prio={q['priority']:.1f} {q['momentum']['arrow']}")
    print("     why:", q["why_priority"][:150])
print("ALERTS:", db.query(Alert).count())
for a in db.query(Alert).all()[:5]:
    print("  ", a.level, a.status, a.location_id, round(a.risk_score,1), "|", a.title[:60])
db.close()
