"""End-to-end API smoke test.

Start the server first:
    PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
then:
    .venv/bin/python scripts/api_smoke.py

Point it at a different instance with the PEHRA_BASE environment variable:
    PEHRA_BASE=http://127.0.0.1:8799 .venv/bin/python scripts/api_smoke.py

Exercises all endpoints including the RBAC denials, validation failures and
the 404 paths. Exits non-zero on any unexpected status code.
"""
import json, os, sys, urllib.request, urllib.error

BASE = os.environ.get("PEHRA_BASE", "http://127.0.0.1:8000")
fails = []

def call(method, path, body=None, token=None, expect=200):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data: req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            code, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read()
    except Exception as e:
        fails.append((method, path, "EXC", str(e))); print(f"  !! {method} {path} EXC {e}"); return None
    ok = code == expect
    mark = "ok " if ok else "FAIL"
    print(f"  {mark} {code:3d} {method:6s} {path}")
    if not ok:
        fails.append((method, path, code, payload[:400].decode('utf-8','replace')))
        print("       ", payload[:300].decode('utf-8','replace'))
    try: return json.loads(payload)
    except Exception: return None

print("— system —")
h = call("GET", "/api/health")
print("     overall:", h["status"], "| degraded:", h["degraded_components"])
call("GET", "/api/config"); call("GET", "/api/system-status")
call("GET", "/api/models"); call("GET", "/api/providers"); call("GET", "/api/hazards")

print("— auth —")
call("GET", "/api/auth/demo-accounts")
call("POST", "/api/auth/login", {"username":"authority","password":"wrongpass"}, expect=401)
tok = call("POST", "/api/auth/login", {"username":"authority","password":"authority123"})["access_token"]
ctok = call("POST", "/api/auth/login", {"username":"citizen","password":"citizen123"})["access_token"]
atok = call("POST", "/api/auth/login", {"username":"admin","password":"admin12345"})["access_token"]
call("GET", "/api/auth/me", token=tok)
call("GET", "/api/auth/users", token=tok, expect=403)
call("GET", "/api/auth/users", token=atok)
call("GET", "/api/logs", token=atok)

print("— reset + scenario —")
call("POST", "/api/simulation/reset", {"scenario_id":"mumbai_mithi"}, token=tok)
call("GET", "/api/simulation/state")
call("POST", "/api/scenarios/mumbai_mithi/run", {"reset_tick":True,"auto_advance_to":12}, token=tok)
call("GET", "/api/scenarios")

print("— risk —")
locs = call("GET", "/api/locations")
print("     locations:", locs["count"])
call("GET", "/api/locations/nearest?lat=19.06&lng=72.88")
call("GET", "/api/locations/loc_kurla")
call("GET", "/api/locations/loc_nope", expect=404)
call("GET", "/api/observations/loc_kurla")
call("GET", "/api/forecast/loc_kurla")
r = call("GET", "/api/risk/loc_kurla?persist=true")
print("     risk:", r["risk"]["overall"], r["risk"]["severity"]["key"], "conf", r["risk"]["confidence"]["value"], "| contributors", len(r["contributors"]))
call("GET", "/api/risk/loc_kurla/timeline")
call("GET", "/api/risk/loc_kurla/history")
call("GET", "/api/risk/cell?lat=19.0697&lng=72.8834")
call("GET", "/api/risk/point?lat=18.4&lng=73.8")
f = call("GET", "/api/map/field"); print("     field points:", f["count"])
ml = call("GET", "/api/map/layers"); print("     zones", len(ml["zones"]), "infra", len(ml["infrastructure"]), "cells", len(ml["threat_cells"]))
t = call("GET", "/api/threats"); print("     threat cells:", t["count"])
if t["count"]:
    cid = t["threat_cells"][0]["id"]; call("GET", f"/api/threats/{cid}")
call("GET", "/api/early-signals")
dh = call("GET", "/api/data-health"); print("     data health:", dh["score"], dh["grade"])
tg = call("GET", "/api/map/topology"); print("     topology layers:", tg["layer_count"], "| categories", ", ".join(c["id"] for c in tg["categories"]))

print("— sim controls —")
call("POST", "/api/simulation/step", {"steps":2}, token=tok)
call("POST", "/api/simulation/overrides", {"rainfall":1.4}, token=tok)
call("POST", "/api/simulation/connectivity", {"mode":"degraded"}, token=tok)
call("POST", "/api/simulation/failure", {"component":"river","enabled":True}, token=tok)
call("POST", "/api/simulation/failure", {"component":"river","enabled":False}, token=tok)
call("POST", "/api/simulation/connectivity", {"mode":"online"}, token=tok)
call("POST", "/api/simulation/model", {"model_key":"statistical"}, token=tok)
call("POST", "/api/simulation/model", {"model_key":"demo"}, token=tok)
call("POST", "/api/simulation/overrides", {}, token=tok)
call("POST", "/api/simulation/refresh", token=tok)
call("POST", "/api/what-if", {"location_id":"loc_kurla","rainfall":1.5,"river_level":1.2})

print("— alerts —")
al = call("GET", "/api/alerts"); print("     alerts:", al["total"])
call("POST", "/api/alerts/preview", {"location_id":"loc_kurla"}, token=tok)
new = call("POST", "/api/alerts", {
  "location_id":"loc_kurla","hazard":"flood","level":"WARNING",
  "message":"Water levels are rising rapidly along the Mithi river bank.",
  "recommended_actions":["Move away from low-lying roads"],
  "geofence":{"kind":"radius","radius_km":6},
}, token=tok, expect=201)
call("POST", "/api/alerts", {"location_id":"loc_kurla","hazard":"flood","level":"WARNING","message":"x"}, token=ctok, expect=403)
call("POST", "/api/alerts", {"location_id":"loc_kurla","hazard":"flood","level":"WARNING","message":"short"}, token=tok, expect=422)
aid = new["id"]
call("GET", f"/api/alerts/{aid}")
call("POST", f"/api/alerts/{aid}/issue", token=tok)
call("POST", f"/api/alerts/{aid}/deliver", token=tok)
call("POST", f"/api/alerts/{aid}/acknowledge", {"note":"Understood"}, token=ctok)
call("PATCH", f"/api/alerts/{aid}", {"level":"CRITICAL","reason":"Situation worsened"}, token=tok)
call("PATCH", f"/api/alerts/{aid}", {"status":"resolved","reason":"Water receded"}, token=tok)
call("GET", "/api/alerts/for-location/loc_kurla")
call("GET", "/api/actions/flood/CRITICAL")
call("GET", "/api/actions/nope/CRITICAL", expect=404)
call("GET", "/api/incidents")

print("— analytics —")
o = call("GET", "/api/overview")
print("     exposed:", o["metrics"]["people_potentially_exposed"], "| critical zones:", o["metrics"]["critical_zones"])
call("GET", "/api/analytics")
mp = call("GET", "/api/analytics/model"); print("     model perf available:", mp["available"])
call("GET", "/api/analytics/compare?sort_by=risk")
call("GET", "/api/audit", token=tok)
call("GET", "/api/audit", token=ctok, expect=403)

print("— replay / verify —")
rp = call("GET", "/api/replay/mumbai_mithi?location_id=loc_kurla")
print("     replay frames:", len(rp.get("frames", [])))
v = call("POST", "/api/verify", {"scenario_id":"mumbai_mithi","location_id":"loc_kurla"}, token=tok)
print("     verify samples:", v.get("sample_size"), "| metrics:", {k: v.get("metrics",{}).get(k) for k in ("precision","recall","f1","mae")})
mp = call("GET", "/api/analytics/model"); print("     model perf now:", mp["available"], mp.get("sample_size"))
call("GET", "/api/events/recent")

print("-- safe navigation / routing --")
prov = call("GET", "/api/routes/providers")
print("     providers:", ", ".join(p["key"] for p in prov["providers"]))
plan = call("POST", "/api/routes/plan", {
    "from_lat": 18.9306, "from_lng": 72.8337,
    "to_lat": 19.0697, "to_lng": 72.8834, "preference": "balanced",
})
print("     route:", plan.get("route_id"), "|", plan.get("risk_level"),
      "| dist", round(plan.get("distance_m", 0) / 1000, 1), "km |", len(plan.get("alternatives", [])), "alternatives")
rid = plan.get("route_id")
call("GET", f"/api/routes/{rid}")
rr = call("POST", f"/api/routes/{rid}/re-route")
print("     re-route changed:", rr.get("changed"), "->", rr.get("risk_level"))
call("GET", "/api/routes/nope", expect=404)
call("POST", "/api/routes/nope/re-route", expect=404)
call("POST", "/api/routes/plan", {
    "from_lat": 18.9306, "from_lng": 72.8337,
    "to_lat": 19.0697, "to_lng": 72.8834, "preference": "teleport",
}, expect=422)
# model/pickle honesty surface
for m in call("GET", "/api/models").get("models", []):
    if m.get("pickle_sklearn") or m.get("runtime_sklearn"):
        print("     model", m["kind"], "| pkl", m.get("pickle_sklearn"),
              "| runtime", m.get("runtime_sklearn"), "| mismatch", m.get("version_mismatch"))

print("-- citizens / People & SOS --")
ps = call("GET", "/api/citizens/personas", token=ctok)
print("     personas:", ps and ps.get("count"), "| simulated:", ps and ps.get("is_simulated"))
call("POST", "/api/citizens/heartbeat", {
    "persona_id": "persona_1", "fix": {"lat": 19.085, "lng": 72.884, "accuracy": 12},
    "announced": "online", "ble_enabled": True, "bt_mode": "native", "battery": 82,
}, token=ctok)
call("POST", "/api/citizens/heartbeat", {
    "persona_id": "persona_2", "fix": {"lat": 18.911, "lng": 72.817, "accuracy": 18},
    "announced": "online", "bt_mode": "simulated",
}, token=ctok)
# citizen asking for help, authority acknowledging + resolving
hp = call("POST", "/api/citizens/persona_3/help", {"message": "Water entering my home, need evacuation help."}, token=ctok)
print("     help state:", hp["help"]["status"], "| simulated:", hp.get("is_simulated"))
call("POST", "/api/citizens/persona_3/help/ack", {"acknowledged_by": "Demo Municipal Officer"}, token=tok)
call("POST", "/api/citizens/persona_3/help/resolve", token=tok)
# relay via nearby phone for an offline persona
call("POST", "/api/citizens/heartbeat", {
    "persona_id": "persona_1", "fix": {"lat": 19.0849, "lng": 72.8841, "accuracy": 15},
    "announced": "relay", "via_relay": "persona_2", "bt_mode": "native",
}, token=ctok)
cv = call("GET", "/api/citizens", token=tok)
print("     citizens:", cv["count"], "| states:", sorted({c["state"] for c in cv["citizens"]}))
relayed = next((c for c in cv["citizens"] if c["state"] == "relay"), None)
if relayed:
    print("     relay:", relayed["codename"], "via", relayed["via_relay"], "| last fix", relayed["last_fix_at"])
call("POST", "/api/citizens/heartbeat", {
    "persona_id": "persona_2", "fix": {"lat": 18.911, "lng": 72.817, "accuracy": 18},
    "announced": "offline", "bt_mode": "simulated",
}, token=ctok)
cv2 = call("GET", "/api/citizens", token=tok)
off = next((c for c in cv2["citizens"] if c["state"] == "offline"), None)
if off:
    print("     offline:", off["codename"], "| last known at", off["last_fix_at"], "| age", off["age_s"])
call("GET", "/api/citizens", token=ctok, expect=403)          # citizen role must not list everyone
call("POST", "/api/citizens/reset", token=tok)
call("GET", "/api/citizens", token=tok)

print()
print("FAILURES:", len(fails))
for f in fails: print("  ", f[0], f[1], f[2], str(f[3])[:200])
sys.exit(1 if fails else 0)
