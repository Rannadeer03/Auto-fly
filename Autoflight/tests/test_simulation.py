"""
Mission Planner — Full Backend Simulation Test
================================================
Tests every layer of the stack against the real estancia.plan file.
No Pixhawk or serial port required: MAVLink I/O is replaced with mocks.

Run from the repo root:
    python3 tests/test_simulation.py
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ── Make the backend package importable ────────────────────────────────────────
BACKEND   = Path(__file__).parent.parent / "backend"
PLAN_FILE = Path(__file__).parent.parent / "estancia.plan"
sys.path.insert(0, str(BACKEND))

# ── Colours ────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
PASS = f"{GREEN}✔ PASS{RESET}"
FAIL = f"{RED}✖ FAIL{RESET}"
INFO = f"{CYAN}ℹ{RESET}"

_results: list[tuple[str, bool, str]] = []

def check(label: str, condition: bool, detail: str = "") -> bool:
    tag = PASS if condition else FAIL
    print(f"  {tag}  {label}" + (f"  →  {detail}" if detail else ""))
    _results.append((label, condition, detail))
    return condition

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL SIMULATION SETUP
# Patches are started ONCE and stay active for the entire test run.
# Individual tests can temporarily override specific methods with local patches.
# ══════════════════════════════════════════════════════════════════════════════

def _start_simulation():
    """
    1. Populate DroneState to simulate a healthy connected drone.
    2. Give the MAVLink connection a fake master so _require_master() passes.
    3. Start persistent patches on MissionUploader and MAVLinkCommands so no
       real serial I/O is attempted.
    """
    from mavlink.connection import drone_state, connection

    drone_state.update(
        connected=True,
        last_heartbeat_time=time.monotonic(),
        heartbeat_count=60,
        flight_mode="STABILIZE",
        armed=False,
        system_status=3,                    # MAV_STATE_STANDBY
        latitude=12.82684804834033,
        longitude=80.05155996696101,
        altitude_msl=48.0,
        altitude_rel=0.0,
        ground_speed=0.0,
        air_speed=0.0,
        heading=47,
        roll=0.1, pitch=-0.2, yaw=47.0,
        gps_fix_type=3,
        gps_satellites=14,
        gps_hdop=0.72,
        gps_vdop=1.05,
        battery_voltage=24.84,
        battery_remaining=97,
        battery_current=2.3,
        battery_consumed_mah=12.0,
        mission_uploaded=False,
        waypoint_count=0,
        current_waypoint=0,
        ekf_ok=True,
        gyro_ok=True,
        accel_ok=True,
        baro_ok=True,
        compass_ok=True,
    )
    # A fake master so _require_master() does not raise RuntimeError
    connection._master  = MagicMock()
    connection._running = True

    # Persistent patches — stay active until .stop() is called
    patchers = [
        patch("mavlink.mission_upload.MissionUploader.upload_mission", return_value=True),
        patch("mavlink.mission_upload.MissionUploader.clear_mission",  return_value=True),
        patch("mavlink.mission_upload.MissionUploader.verify_mission",
              return_value=(True, "Mission verified: 8 items match.")),
        patch("mavlink.commands.MAVLinkCommands.arm",           return_value=True),
        patch("mavlink.commands.MAVLinkCommands.disarm",        return_value=True),
        patch("mavlink.commands.MAVLinkCommands.start_auto",    return_value=True),
        patch("mavlink.commands.MAVLinkCommands.pause",         return_value=True),
        patch("mavlink.commands.MAVLinkCommands.resume",        return_value=True),
        patch("mavlink.commands.MAVLinkCommands.rtl",           return_value=True),
        patch("mavlink.commands.MAVLinkCommands.land",          return_value=True),
        patch("mavlink.commands.MAVLinkCommands.emergency_stop",return_value=True),
    ]
    mocks = [p.start() for p in patchers]
    return patchers, mocks


def _make_client():
    from starlette.testclient import TestClient
    from app import app
    return TestClient(app, raise_server_exceptions=False)


def _refresh_heartbeat():
    """Keep the simulated heartbeat alive so heartbeat_ok stays True."""
    from mavlink.connection import drone_state
    drone_state.update(last_heartbeat_time=time.monotonic())


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Parser layer (no HTTP, no mocks needed)
# ══════════════════════════════════════════════════════════════════════════════

def test_plan_parser():
    print(f"\n{BOLD}{CYAN}── Phase 1: QGC .plan Parser ─────────────────────────────────{RESET}")
    from parser.plan_parser import QGCPlanParser
    from models.mission import Mission

    raw     = PLAN_FILE.read_bytes()
    mission = QGCPlanParser().parse_bytes(raw, "estancia.plan")

    check("parse_bytes() returns a Mission",      isinstance(mission, Mission))
    check("source_format == 'plan'",              mission.source_format == "plan",
          f"got '{mission.source_format}'")

    # home(1) + TAKEOFF(1) + NAV_WP(5) + RTL(1) = 8
    check("waypoint_count == 8",                  mission.waypoint_count == 8,
          f"got {mission.waypoint_count}")
    # nav_waypoints excludes home (current=True) → 5 NAV_WP items
    check("nav_waypoints == 5",                   mission.nav_waypoints == 5,
          f"got {mission.nav_waypoints}")

    home = mission.waypoints[0]
    check("waypoints[0].current is True",         home.current is True)
    check("waypoints[0].index == 0",              home.index == 0)
    check("home latitude correct",
          abs(home.latitude  - 12.82684804834033) < 1e-6, f"got {home.latitude}")
    check("home longitude correct",
          abs(home.longitude - 80.05155996696101) < 1e-6, f"got {home.longitude}")
    check("home altitude == 48 m AMSL",           abs(home.altitude - 48.0) < 0.001,
          f"got {home.altitude}")

    takeoff = mission.waypoints[1]
    check("waypoints[1] is TAKEOFF (cmd=22)",     takeoff.command == 22,
          f"got cmd={takeoff.command}")

    last = mission.waypoints[-1]
    check("waypoints[-1] is RTL (cmd=20)",        last.command == 20,
          f"got cmd={last.command}")

    nav_alts = [w.altitude for w in mission.waypoints if w.command == 16 and not w.current]
    check("all mission NAV_WP altitudes == 6.096 m",
          all(abs(a - 6.096) < 0.001 for a in nav_alts), f"alts={nav_alts}")

    check("total_distance_m > 0",                 mission.total_distance_m > 0,
          f"{mission.total_distance_m} m")
    check("estimated_duration_minutes > 0",       mission.estimated_duration_minutes > 0,
          f"{mission.estimated_duration_minutes} min")

    print(f"  {INFO}  Distance: {mission.total_distance_m} m  "
          f"Duration: {mission.estimated_duration_minutes} min  "
          f"Battery: {mission.estimated_battery_percent}%")
    return mission


def test_waypoints_parser_rejects_plan():
    print(f"\n{BOLD}{CYAN}── Phase 1b: .waypoints parser rejects .plan bytes ──────────{RESET}")
    from parser.waypoint_parser import QGCWaypointParser, WaypointParseError
    raw = PLAN_FILE.read_bytes()
    try:
        QGCWaypointParser().parse_bytes(raw, "x.waypoints")
        check("raises WaypointParseError on plan content", False, "no exception")
    except WaypointParseError as e:
        check("raises WaypointParseError on plan content", True, str(e)[:60])


def test_loader():
    print(f"\n{BOLD}{CYAN}── Phase 2: Loader dispatch ─────────────────────────────────{RESET}")
    from parser.loader import load_mission, supported_extensions
    from parser.waypoint_parser import WaypointParseError

    raw = PLAN_FILE.read_bytes()

    m = load_mission("estancia.plan", raw)
    check("loader → plan parser for .plan",       m.source_format == "plan")

    try:
        load_mission("flight.kml", raw)
        check("loader rejects .kml", False, "no exception")
    except WaypointParseError as e:
        check("loader rejects .kml", True, str(e)[:60])

    exts = supported_extensions()
    check("supported: .plan and .waypoints",
          ".plan" in exts and ".waypoints" in exts, str(exts))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — API layer
# ══════════════════════════════════════════════════════════════════════════════

def test_health(client):
    print(f"\n{BOLD}{CYAN}── Phase 3a: GET /health ────────────────────────────────────{RESET}")
    r    = client.get("/health")
    body = r.json()
    check("status 200",               r.status_code == 200,   str(r.status_code))
    check("status == 'ok'",           body.get("status") == "ok")
    check("version == '1.0.0'",       body.get("version") == "1.0.0")
    check("drone_connected == True",  body.get("drone_connected") is True)


def test_telemetry(client):
    print(f"\n{BOLD}{CYAN}── Phase 3b: GET /telemetry ─────────────────────────────────{RESET}")
    r = client.get("/telemetry")
    check("status 200",               r.status_code == 200, str(r.status_code))
    t = r.json()
    check("connected == True",        t["connected"] is True)
    check("armed == False",           t["armed"] is False)
    check("flight_mode == STABILIZE", t["flight_mode"] == "STABILIZE", t["flight_mode"])
    check("gps fix_type == 3",        t["gps"]["fix_type"] == 3)
    check("gps satellites == 14",     t["gps"]["satellites_visible"] == 14)
    check("battery voltage ≈ 24.84",
          abs(t["battery"]["voltage"] - 24.84) < 0.01, str(t["battery"]["voltage"]))
    check("battery remaining == 97",  t["battery"]["remaining_percent"] == 97)
    check("position latitude OK",
          abs(t["position"]["latitude"] - 12.82684804834033) < 1e-4)
    check("health.ekf_ok == True",    t["health"]["ekf_ok"] is True)
    check("link_quality == 100%",     t["link_quality_percent"] == 100.0,
          str(t["link_quality_percent"]))
    print(f"  {INFO}  Mode: {t['flight_mode']}  "
          f"GPS: {t['gps']['fix_type_str']}  "
          f"Batt: {t['battery']['voltage']}V/{t['battery']['remaining_percent']}%")


def test_upload(client):
    print(f"\n{BOLD}{CYAN}── Phase 3c: POST /upload (estancia.plan) ───────────────────{RESET}")
    _refresh_heartbeat()
    raw = PLAN_FILE.read_bytes()
    r   = client.post("/upload",
                      files={"file": ("estancia.plan", raw, "application/octet-stream")})
    check("status 200",               r.status_code == 200,  str(r.status_code))
    body = r.json()
    check("success == True",          body.get("success") is True)
    check("uploaded_to_drone == True",body.get("uploaded_to_drone") is True)
    check("verified == True",         body.get("verified") is True,
          body.get("verification_message", ""))

    mi = body.get("mission_info", {})
    check("mission_info present",     bool(mi))
    check("source_format == 'plan'",  mi.get("source_format") == "plan",
          mi.get("source_format"))
    check("waypoint_count == 8",      mi.get("waypoint_count") == 8,
          str(mi.get("waypoint_count")))
    check("nav_waypoints == 5",       mi.get("nav_waypoints") == 5,
          str(mi.get("nav_waypoints")))
    check("filename preserved",       "estancia" in mi.get("filename", ""),
          mi.get("filename"))
    check("total_distance_m > 0",     mi.get("total_distance_m", 0) > 0,
          f"{mi.get('total_distance_m')} m")
    check("max_altitude_m > 0",       mi.get("max_altitude_m", 0) > 0)

    print(f"  {INFO}  {mi.get('waypoint_count')} waypoints  "
          f"{mi.get('total_distance_m')} m  "
          f"~{mi.get('estimated_duration_minutes')} min  "
          f"~{mi.get('estimated_battery_percent')}% battery")


def test_mission_status(client):
    print(f"\n{BOLD}{CYAN}── Phase 3d: GET /mission ───────────────────────────────────{RESET}")
    r  = client.get("/mission")
    ms = r.json()
    check("status 200",               r.status_code == 200, str(r.status_code))
    check("uploaded == True",         ms["uploaded"] is True)
    check("waypoint_count == 8",      ms["waypoint_count"] == 8, str(ms["waypoint_count"]))
    check("mission_info present",     ms.get("mission_info") is not None)
    check("source_format == 'plan'",
          ms.get("mission_info", {}).get("source_format") == "plan")


def test_arm_safety_checks(client):
    print(f"\n{BOLD}{CYAN}── Phase 3e: POST /arm — safety checks ──────────────────────{RESET}")
    from mavlink.connection import drone_state
    _refresh_heartbeat()

    # ARM with healthy state (uploader already mocked globally)
    drone_state.update(battery_voltage=24.84, battery_remaining=97,
                       gps_fix_type=3, gps_satellites=14, mission_uploaded=True)
    r = client.post("/arm")
    check("ARM succeeds — healthy state",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message", "")[:60])

    # ARM blocked: battery too low
    drone_state.update(battery_remaining=10, battery_voltage=21.0)
    r = client.post("/arm")
    check("ARM blocked — battery low",
          not r.json()["success"], r.json().get("message","")[:70])
    drone_state.update(battery_remaining=97, battery_voltage=24.84)

    # ARM blocked: poor GPS
    drone_state.update(gps_fix_type=1, gps_satellites=2)
    r = client.post("/arm")
    check("ARM blocked — poor GPS",
          not r.json()["success"], r.json().get("message","")[:70])
    drone_state.update(gps_fix_type=3, gps_satellites=14)

    # ARM blocked: no mission
    drone_state.update(mission_uploaded=False)
    r = client.post("/arm")
    check("ARM blocked — no mission",
          not r.json()["success"], r.json().get("message","")[:70])
    drone_state.update(mission_uploaded=True)


def test_flight_command_sequence(client):
    print(f"\n{BOLD}{CYAN}── Phase 3f: Flight command sequence ────────────────────────{RESET}")
    from mavlink.connection import drone_state
    _refresh_heartbeat()

    drone_state.update(armed=True, flight_mode="STABILIZE",
                       mission_uploaded=True, ekf_ok=True, gps_fix_type=3)

    # START MISSION
    r = client.post("/start")
    check("START — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])
    drone_state.update(flight_mode="AUTO")

    # PAUSE
    r = client.post("/pause")
    check("PAUSE — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])
    drone_state.update(flight_mode="LOITER")

    # RESUME
    r = client.post("/resume")
    check("RESUME — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])
    drone_state.update(flight_mode="AUTO")

    # RTL
    r = client.post("/rtl")
    check("RTL — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])

    # LAND
    r = client.post("/land")
    check("LAND — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])

    # DISARM
    r = client.post("/disarm")
    check("DISARM — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])
    drone_state.update(armed=False, flight_mode="STABILIZE")

    # EMERGENCY STOP
    r = client.post("/emergency_stop")
    check("EMERGENCY STOP — success",
          r.status_code == 200 and r.json()["success"] is True,
          r.json().get("message","")[:50])


def test_start_blocked_ekf(client):
    print(f"\n{BOLD}{CYAN}── Phase 3g: START blocked when EKF unhealthy ───────────────{RESET}")
    from mavlink.connection import drone_state
    drone_state.update(armed=True, ekf_ok=False, mission_uploaded=True)
    r = client.post("/start")
    check("START blocked — EKF not healthy",
          not r.json()["success"], r.json().get("message","")[:70])
    drone_state.update(ekf_ok=True)


def test_clear_mission(client):
    print(f"\n{BOLD}{CYAN}── Phase 3h: POST /clear ────────────────────────────────────{RESET}")
    r = client.post("/clear")
    check("status 200",               r.status_code == 200, str(r.status_code))
    check("success == True",          r.json()["success"] is True)
    from mavlink.connection import drone_state
    check("drone_state.mission_uploaded reset",
          drone_state.mission_uploaded is False)


def test_rejection_wrong_extension(client):
    print(f"\n{BOLD}{CYAN}── Phase 3i: Rejection — wrong extension (.kml) ─────────────{RESET}")
    r = client.post("/upload",
                    files={"file": ("mission.kml", b"<kml/>", "application/xml")})
    check("status 400",               r.status_code == 400, str(r.status_code))
    detail = r.json().get("detail", "").lower()
    check("error mentions format",
          "kml" in detail or "supported" in detail or "not accepted" in detail,
          r.json().get("detail","")[:70])


def test_rejection_corrupted_json(client):
    print(f"\n{BOLD}{CYAN}── Phase 3j: Rejection — corrupted .plan (bad JSON) ─────────{RESET}")
    r = client.post("/upload",
                    files={"file": ("bad.plan", b"{not json!!", "application/octet-stream")})
    check("status 400",               r.status_code == 400, str(r.status_code))
    detail = r.json().get("detail", "").lower()
    check("error mentions JSON / invalid",
          "json" in detail or "invalid" in detail, r.json().get("detail","")[:70])


def test_rejection_wrong_filetype(client):
    print(f"\n{BOLD}{CYAN}── Phase 3k: Rejection — wrong fileType in .plan ─────────────{RESET}")
    bad = json.dumps({"fileType": "NotAPlan", "mission": {}}).encode()
    r = client.post("/upload",
                    files={"file": ("wrong.plan", bad, "application/octet-stream")})
    check("status 400",               r.status_code == 400, str(r.status_code))
    detail = r.json().get("detail", "").lower()
    check("error mentions Plan / fileType",
          "plan" in detail or "filetype" in detail, r.json().get("detail","")[:70])


def test_rejection_empty_file(client):
    print(f"\n{BOLD}{CYAN}── Phase 3l: Rejection — empty file ─────────────────────────{RESET}")
    r = client.post("/upload",
                    files={"file": ("empty.plan", b"", "application/octet-stream")})
    check("status 400",               r.status_code == 400, str(r.status_code))
    detail = r.json().get("detail", "").lower()
    check("error mentions empty",     "empty" in detail, r.json().get("detail","")[:70])


def test_logs(client):
    print(f"\n{BOLD}{CYAN}── Phase 3m: GET /logs ──────────────────────────────────────{RESET}")
    r    = client.get("/logs?count=50")
    body = r.json()
    check("status 200",               r.status_code == 200, str(r.status_code))
    check("'logs' key present",       "logs" in body)
    logs = body["logs"]
    check("logs is a list",           isinstance(logs, list))
    if logs:
        e = logs[0]
        check("entry has 'level'",    "level" in e)
        check("entry has 'msg'",      "msg"   in e)
        check("entry has 'ts'",       "ts"    in e)
    print(f"  {INFO}  {len(logs)} log entries returned.")


def test_disconnect(client):
    print(f"\n{BOLD}{CYAN}── Phase 3n: POST /disconnect ───────────────────────────────{RESET}")
    from mavlink.connection import drone_state, connection
    with patch.object(connection, "disconnect",
                      side_effect=lambda: drone_state.update(connected=False)):
        r = client.post("/disconnect")
    check("status 200",               r.status_code == 200, str(r.status_code))
    check("success == True",          r.json()["success"] is True)
    check("drone reports disconnected", drone_state.connected is False)


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}  Mission Planner — Backend Simulation Test Suite{RESET}")
    print(f"{BOLD}  Mission file: {PLAN_FILE.name}{RESET}")
    print(f"{BOLD}{'═'*62}{RESET}")

    if not PLAN_FILE.exists():
        print(f"{RED}ERROR: {PLAN_FILE} not found.{RESET}")
        sys.exit(1)

    # ── Parser / loader tests — no mocks ──────────────────────────────────
    test_plan_parser()
    test_waypoints_parser_rejects_plan()
    test_loader()

    # ── Start persistent MAVLink simulation ───────────────────────────────
    patchers, _ = _start_simulation()

    try:
        client = _make_client()

        # ── API tests ──────────────────────────────────────────────────────
        test_health(client)
        test_telemetry(client)
        test_upload(client)
        test_mission_status(client)
        test_arm_safety_checks(client)
        test_flight_command_sequence(client)
        test_start_blocked_ekf(client)
        test_clear_mission(client)
        test_rejection_wrong_extension(client)
        test_rejection_corrupted_json(client)
        test_rejection_wrong_filetype(client)
        test_rejection_empty_file(client)
        test_logs(client)
        test_disconnect(client)

    finally:
        for p in patchers:
            p.stop()

    # ── Summary ────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    print(f"\n{BOLD}{'═'*62}{RESET}")
    colour = GREEN if failed == 0 else RED
    print(f"{BOLD}  Results: {colour}{passed}/{total} passed{RESET}", end="")
    if failed:
        print(f"  {RED}({failed} failed){RESET}", end="")
    print()

    if failed:
        print(f"\n{RED}  Failed checks:{RESET}")
        for label, ok, detail in _results:
            if not ok:
                print(f"    {RED}✖{RESET}  {label}")
                if detail:
                    print(f"         {YELLOW}{detail}{RESET}")

    print(f"{BOLD}{'═'*62}{RESET}\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
