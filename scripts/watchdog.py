#!/usr/bin/env python3
"""
watchdog.py - Automated monitoring and self-healing watchdog for OpenShorts.
Checks systemd services, API health, active jobs, and YouTube auto-posting status.
"""
import os
import sys
import time
import subprocess
import requests

sys.path.insert(0, "/root/openshort")

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5175"
NGINX_URL = "http://127.0.0.1"
LOG_FILE = "/root/openshort/output/watchdog.log"


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def check_and_heal():
    log("🔍 Watchdog health check initiated...")

    # 1. Check systemd services
    services = ["openshort-backend.service", "openshort-frontend.service", "nginx"]
    for svc in services:
        res = subprocess.run(["systemctl", "is-active", "--quiet", svc])
        if res.returncode != 0:
            log(f"⚠️ Service {svc} was down! Restarting...")
            subprocess.run(["systemctl", "restart", svc])
            time.sleep(2)
            log(f"✅ Service {svc} restarted.")

    # 2. Check Backend API response
    try:
        r = requests.get(f"{BACKEND_URL}/api/config", timeout=6)
        if r.status_code == 200:
            log("✅ Backend API is healthy (HTTP 200).")
        else:
            log(f"⚠️ Backend API returned status {r.status_code}. Restarting backend...")
            subprocess.run(["systemctl", "restart", "openshort-backend.service"])
    except Exception as e:
        log(f"❌ Backend API check failed ({e}). Restarting backend...")
        subprocess.run(["systemctl", "restart", "openshort-backend.service"])

    # 3. Check Frontend UI response
    try:
        r = requests.get(FRONTEND_URL, timeout=6)
        if r.status_code == 200:
            log("✅ Frontend UI is healthy (HTTP 200).")
        else:
            log(f"⚠️ Frontend returned status {r.status_code}. Restarting frontend...")
            subprocess.run(["systemctl", "restart", "openshort-frontend.service"])
    except Exception as e:
        log(f"❌ Frontend check failed ({e}). Restarting frontend...")
        subprocess.run(["systemctl", "restart", "openshort-frontend.service"])

    # 4. Check YouTube Connection status
    try:
        r = requests.get(f"{BACKEND_URL}/api/youtube/config", timeout=6)
        if r.status_code == 200:
            yt_cfg = r.json()
            if yt_cfg.get("configured"):
                log("🎉 YouTube Auto-Post: Connected and ready.")
            else:
                log("ℹ️ YouTube Auto-Post: OAuth pending. Authorize anytime at https://evworx.co.in/api/youtube/auth/login")
    except Exception as e:
        log(f"⚠️ YouTube config check error: {e}")

    # 5. Check and recover any stale autopilot jobs
    try:
        from autopilot.database import AutopilotDatabase
        from autopilot.config import AutopilotConfig
        from autopilot.models import JobStatus
        cfg = AutopilotConfig.from_env()
        if cfg.database_path.exists():
            db = AutopilotDatabase(cfg.database_path)
            with db.transaction() as conn:
                stale = conn.execute("""
                    SELECT COUNT(*) as cnt FROM processing_jobs 
                    WHERE (status = 'claimed' OR UPPER(status) = 'PROCESSING')
                      AND locked_at < datetime('now', '-30 minutes')
                """).fetchone()
                if stale and stale["cnt"] > 0:
                    conn.execute("""
                        UPDATE processing_jobs 
                        SET status = 'QUEUED', locked_at = NULL, worker_id = NULL
                        WHERE (status = 'claimed' OR UPPER(status) = 'PROCESSING')
                          AND locked_at < datetime('now', '-30 minutes')
                    """)
                    log(f"♻️ Watchdog recovered {stale['cnt']} stale processing jobs to QUEUED.")

                # If there are queued jobs waiting (orphaned for > 45 seconds), process them
                queued = conn.execute("""
                    SELECT id FROM processing_jobs 
                    WHERE UPPER(status) = 'QUEUED'
                      AND (created_at IS NULL OR created_at < datetime('now', '-45 seconds'))
                    LIMIT 2
                """).fetchall()
                if queued:
                    log(f"⚡ Watchdog found {len(queued)} queued jobs waiting. Processing existing queued jobs...")
                    from autopilot.orchestrator import AutopilotOrchestrator
                    orch = AutopilotOrchestrator(cfg)
                    for qrow in queued:
                        try:
                            orch.process_job_by_id(qrow["id"])
                        except Exception as jerr:
                            log(f"⚠️ Error processing queued job {qrow['id']}: {jerr}")
    except Exception as e:
        log(f"⚠️ Autopilot watchdog check note: {e}")

    log("🏁 Watchdog check complete.\n")


if __name__ == "__main__":
    check_and_heal()
