#!/usr/bin/env python3
"""Pi Dashboard server - exposes /api/stats, /api/memory, /api/history and serves index.html on port 8080."""

import collections
import json
import os
import sqlite3
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MINDMAP_DIR = Path("/home/felipe/sources/pi-dashboard/mindmaps")
MINDMAP_DIR.mkdir(exist_ok=True)

HISTORY_MAXLEN = 60  # 60 samples × 5s = 5 minutes
_history_lock = threading.Lock()
_history: collections.deque = collections.deque(maxlen=HISTORY_MAXLEN)


def _collect_history():
    """Background thread: record cpu_percent and ram percent every 5 seconds."""
    while True:
        try:
            cpu = read_cpu_usage()
            ram = read_ram_usage()
            entry = {
                "ts": time.strftime("%H:%M:%S"),
                "cpu": cpu,
                "ram": ram["percent"],
            }
            with _history_lock:
                _history.append(entry)
        except Exception:
            pass
        time.sleep(5)

ENGRAM_DB = os.path.expanduser("~/.engram/engram.db")

TASKS_FILE = Path("/home/felipe/.openclaw/workspace/TASKS.md")
SUMMARY_FILE = Path("/home/felipe/.openclaw/workspace/SUMMARY.md")


def read_tasks():
    try:
        content = TASKS_FILE.read_text() if TASKS_FILE.exists() else "(sin tasks)"
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(TASKS_FILE.stat().st_mtime)) if TASKS_FILE.exists() else ""
        return {"content": content, "updated_at": updated}
    except Exception as e:
        return {"content": f"Error leyendo TASKS.md: {e}", "updated_at": ""}


def read_summary():
    try:
        content = SUMMARY_FILE.read_text() if SUMMARY_FILE.exists() else "(sin resumen)"
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SUMMARY_FILE.stat().st_mtime)) if SUMMARY_FILE.exists() else ""
        return {"content": content, "updated_at": updated}
    except Exception as e:
        return {"content": f"Error leyendo SUMMARY.md: {e}", "updated_at": ""}



def read_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def read_cpu_usage():
    """Read CPU usage by sampling /proc/stat twice with a short interval."""
    def read_stat():
        with open("/proc/stat") as f:
            line = f.readline()
        fields = list(map(int, line.split()[1:]))
        idle = fields[3]
        total = sum(fields)
        return idle, total

    idle1, total1 = read_stat()
    time.sleep(0.2)
    idle2, total2 = read_stat()

    delta_idle = idle2 - idle1
    delta_total = total2 - total1
    if delta_total == 0:
        return 0.0
    return round((1 - delta_idle / delta_total) * 100, 1)


def read_ram_usage():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            info[parts[0].rstrip(":")] = int(parts[1])
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    used = total - available
    percent = round(used / total * 100, 1) if total else 0
    return {
        "total_mb": round(total / 1024, 1),
        "used_mb": round(used / 1024, 1),
        "percent": percent,
    }


def read_disk_usage(path="/"):
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - free
    percent = round(used / total * 100, 1) if total else 0
    return {
        "total_gb": round(total / 1024 ** 3, 1),
        "used_gb": round(used / 1024 ** 3, 1),
        "percent": percent,
    }


def read_load_average():
    with open("/proc/loadavg") as f:
        parts = f.read().split()
    return {
        "1min": float(parts[0]),
        "5min": float(parts[1]),
        "15min": float(parts[2]),
    }


def read_uptime():
    with open("/proc/uptime") as f:
        seconds = float(f.read().split()[0])
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def read_top_processes(n=5):
    """Read top N processes by CPU from /proc/[pid]/stat."""
    procs = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except Exception:
        return []

    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read().split()
            # comm is field 2 (index 1), wrapped in parens
            name = stat[1].strip("()")
            utime = int(stat[13])
            stime = int(stat[14])
            cpu_time = utime + stime

            with open(f"/proc/{pid}/status") as f:
                status_lines = f.readlines()
            vm_rss = 0
            for line in status_lines:
                if line.startswith("VmRSS:"):
                    vm_rss = int(line.split()[1])
                    break

            procs.append({"pid": int(pid), "name": name, "cpu_time": cpu_time, "mem_kb": vm_rss})
        except Exception:
            continue

    # Sort by accumulated CPU time (approximation; no per-interval sampling here)
    procs.sort(key=lambda p: p["cpu_time"], reverse=True)
    top = procs[:n]

    # Convert mem to MB, drop raw cpu_time
    result = []
    for p in top:
        result.append({
            "pid": p["pid"],
            "name": p["name"],
            "cpu_time": p["cpu_time"],
            "mem_mb": round(p["mem_kb"] / 1024, 1),
        })
    return result


def get_stats():
    return {
        "cpu_percent": read_cpu_usage(),
        "ram": read_ram_usage(),
        "disk": read_disk_usage(),
        "cpu_temp_c": read_cpu_temp(),
        "load": read_load_average(),
        "uptime": read_uptime(),
        "top_processes": read_top_processes(),
    }


def get_history():
    with _history_lock:
        items = list(_history)
    return {
        "timestamps": [e["ts"] for e in items],
        "cpu": [e["cpu"] for e in items],
        "ram": [e["ram"] for e in items],
    }


_PRIORITY_SERVICES = {"openclaw", "engram", "ssh"}


def get_services():
    """Return list of systemd services with name, load, active, sub, description."""
    try:
        result = subprocess.run(
            [
                "systemctl", "list-units",
                "--type=service",
                "--state=running,failed,inactive",
                "--no-pager",
                "--plain",
                "--no-legend",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        services = {}
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            unit = parts[0]
            if not unit.endswith(".service"):
                continue
            name = unit[:-len(".service")]
            svc = {
                "name": name,
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": parts[4].strip() if len(parts) > 4 else "",
            }
            services[name] = svc

        # Ensure priority services are included even if not matched by state filter
        for svc_name in _PRIORITY_SERVICES:
            if svc_name in services:
                continue
            r2 = subprocess.run(
                ["systemctl", "show", f"{svc_name}.service",
                 "--property=LoadState,ActiveState,SubState,Description"],
                capture_output=True, text=True, timeout=5,
            )
            if r2.returncode != 0:
                continue
            props = {}
            for ln in r2.stdout.splitlines():
                if "=" in ln:
                    k, v = ln.split("=", 1)
                    props[k] = v
            if not props.get("LoadState"):
                continue
            services[svc_name] = {
                "name": svc_name,
                "load": props.get("LoadState", ""),
                "active": props.get("ActiveState", ""),
                "sub": props.get("SubState", ""),
                "description": props.get("Description", ""),
            }

        # Sort: priority services first, then alphabetical
        def sort_key(s):
            return (0 if s["name"] in _PRIORITY_SERVICES else 1, s["name"])

        return sorted(services.values(), key=sort_key)
    except Exception as e:
        return {"error": str(e), "services": []}


ALERT_THRESHOLDS = {
    "cpu":  {"warning": 75, "critical": 85},
    "ram":  {"warning": 70, "critical": 80},
    "temp": {"warning": 65, "critical": 70},
    "disk": {"warning": 80, "critical": 90},
}


SESSIONS_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")
SESSIONS_JSON = os.path.join(SESSIONS_DIR, "sessions.json")


def get_subagents():
    """Read openclaw sessions.json and return recent/active sessions."""
    if not os.path.exists(SESSIONS_JSON):
        return {"error": "sessions.json not found", "sessions": []}
    try:
        with open(SESSIONS_JSON) as f:
            data = json.load(f)

        sessions = []
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            # Skip individual cron run entries (too many, low signal)
            if ":run:" in key:
                continue
            updated_at = val.get("updatedAt")  # ms epoch
            label = val.get("label") or key.split(":")[-1]
            model = val.get("model", "")
            total_tokens = val.get("totalTokens", 0)
            session_id = val.get("sessionId", "")

            # Derive a type tag from the key
            if ":subagent:" in key:
                kind = "subagent"
            elif ":cron:" in key:
                kind = "cron"
            elif ":telegram:" in key:
                kind = "telegram"
            elif key.endswith(":main"):
                kind = "main"
            else:
                kind = "other"

            sessions.append({
                "key": key,
                "label": label,
                "kind": kind,
                "model": model,
                "total_tokens": total_tokens,
                "session_id": session_id,
                "updated_at_ms": updated_at,
            })

        # Sort by most recently updated, return top 30
        sessions.sort(key=lambda s: s.get("updated_at_ms") or 0, reverse=True)
        return {"sessions": sessions[:30]}
    except Exception as e:
        return {"error": str(e), "sessions": []}

def _summarize_session(session_id):
    """Return (result_text, is_error) from a session jsonl file."""
    if not session_id:
        return "", False
    path = Path(SESSIONS_DIR) / f"{session_id}.jsonl"
    if not path.exists():
        return "", False

    last_text = ""
    last_tool_text = ""
    is_error = False
    try:
        for line in path.read_text().splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message", {})
            role = msg.get("role")
            if role == "toolResult":
                if msg.get("isError"):
                    is_error = True
                parts = [c.get("text", "") for c in msg.get("content", []) if c.get("text")]
                if parts:
                    last_tool_text = " ".join(parts).strip()
            elif role == "assistant":
                parts = [c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text" and c.get("text")]
                if parts:
                    last_text = " ".join(parts).strip()
                    low = last_text.lower()
                    if "error" in low or "fail" in low:
                        is_error = True
    except Exception:
        return "", False

    return (last_text or last_tool_text or ""), is_error


def get_subagent_history(session_key, limit=20):
    if not os.path.exists(SESSIONS_JSON):
        return {"error": "sessions.json not found", "history": []}
    if not session_key:
        return {"error": "missing key", "history": []}

    try:
        with open(SESSIONS_JSON) as f:
            data = json.load(f)

        run_prefix = f"{session_key}:run:"
        run_keys = [k for k in data.keys() if k.startswith(run_prefix)]
        runs = []
        for key in run_keys:
            val = data.get(key) or {}
            updated_at = val.get("updatedAt")
            label = val.get("label") or session_key.split(":")[-1]
            session_id = val.get("sessionId", "")
            result_text, is_error = _summarize_session(session_id)
            runs.append({
                "run_key": key,
                "task": label,
                "updated_at_ms": updated_at,
                "result": result_text,
                "status": "error" if is_error else "ok",
            })

        runs.sort(key=lambda r: r.get("updated_at_ms") or 0, reverse=True)
        return {"history": runs[:limit]}
    except Exception as e:
        return {"error": str(e), "history": []}




def get_logs(n=100):
    """Run journalctl and return last n lines as a list of strings."""
    try:
        result = subprocess.run(
            ["journalctl", f"-n{n}", "--no-pager", "-o", "short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.splitlines()
        return {"lines": lines}
    except Exception as e:
        return {"error": str(e), "lines": []}


def get_alerts():
    alerts = []
    try:
        cpu = read_cpu_usage()
        th = ALERT_THRESHOLDS["cpu"]
        if cpu >= th["critical"]:
            alerts.append({"level": "critical", "metric": "cpu", "value": cpu,
                           "threshold": th["critical"], "message": f"CPU at {cpu}% (threshold {th['critical']}%)"})
        elif cpu >= th["warning"]:
            alerts.append({"level": "warning", "metric": "cpu", "value": cpu,
                           "threshold": th["warning"], "message": f"CPU at {cpu}% (threshold {th['warning']}%)"})
    except Exception:
        pass

    try:
        ram = read_ram_usage()
        th = ALERT_THRESHOLDS["ram"]
        pct = ram["percent"]
        if pct >= th["critical"]:
            alerts.append({"level": "critical", "metric": "ram", "value": pct,
                           "threshold": th["critical"], "message": f"RAM at {pct}% (threshold {th['critical']}%)"})
        elif pct >= th["warning"]:
            alerts.append({"level": "warning", "metric": "ram", "value": pct,
                           "threshold": th["warning"], "message": f"RAM at {pct}% (threshold {th['warning']}%)"})
    except Exception:
        pass

    try:
        temp = read_cpu_temp()
        if temp is not None:
            th = ALERT_THRESHOLDS["temp"]
            if temp >= th["critical"]:
                alerts.append({"level": "critical", "metric": "temp", "value": temp,
                               "threshold": th["critical"], "message": f"CPU temp at {temp}°C (threshold {th['critical']}°C)"})
            elif temp >= th["warning"]:
                alerts.append({"level": "warning", "metric": "temp", "value": temp,
                               "threshold": th["warning"], "message": f"CPU temp at {temp}°C (threshold {th['warning']}°C)"})
    except Exception:
        pass

    try:
        disk = read_disk_usage()
        th = ALERT_THRESHOLDS["disk"]
        pct = disk["percent"]
        if pct >= th["critical"]:
            alerts.append({"level": "critical", "metric": "disk", "value": pct,
                           "threshold": th["critical"], "message": f"Disk at {pct}% (threshold {th['critical']}%)"})
        elif pct >= th["warning"]:
            alerts.append({"level": "warning", "metric": "disk", "value": pct,
                           "threshold": th["warning"], "message": f"Disk at {pct}% (threshold {th['warning']}%)"})
    except Exception:
        pass

    return alerts


def get_memory(query=None):
    """Return observations from engram.db, optionally filtered by query string."""
    if not os.path.exists(ENGRAM_DB):
        return {"error": "engram.db not found", "observations": []}
    try:
        conn = sqlite3.connect(f"file:{ENGRAM_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if query:
            like = f"%{query}%"
            cur.execute(
                """SELECT id, type, title, content, project, created_at
                   FROM observations
                   WHERE deleted_at IS NULL
                     AND (title LIKE ? OR content LIKE ?)
                   ORDER BY created_at DESC""",
                (like, like),
            )
        else:
            cur.execute(
                """SELECT id, type, title, content, project, created_at
                   FROM observations
                   WHERE deleted_at IS NULL
                   ORDER BY created_at DESC"""
            )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"observations": rows}
    except Exception as e:
        return {"error": str(e), "observations": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Suppress default access log noise; print only errors
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/subagents":
            try:
                data = get_subagents()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        if parsed.path == "/api/subagent-history":
            qs = urllib.parse.parse_qs(parsed.query)
            key = qs.get("key", [""])[0]
            limit = qs.get("limit", ["20"])[0]
            try:
                limit = int(limit)
            except Exception:
                limit = 20
            try:
                data = get_subagent_history(key, limit=limit)
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if parsed.path == "/api/alerts":
            try:
                data = get_alerts()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if parsed.path == "/api/logs":
            try:
                data = get_logs()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if parsed.path == "/api/services":
            try:
                data = get_services()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if parsed.path == "/api/memory":
            qs = urllib.parse.parse_qs(parsed.query)
            query = qs.get("q", [None])[0]
            try:
                data = get_memory(query)
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if parsed.path == "/api/tasks":
            try:
                data = read_tasks()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        if parsed.path == "/api/summary":
            try:
                data = read_summary()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return

        if parsed.path == "/api/history":
            try:
                data = get_history()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
            return
        if self.path == "/api/stats":
            try:
                data = get_stats()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path in ("/", "/index.html"):
            index_path = os.path.join(os.path.dirname(__file__), "index.html")
            try:
                with open(index_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"index.html not found")
        elif parsed.path.startswith("/mindmap/"):
            mindmap_id = parsed.path.split("/mindmap/")[1]
            mindmap_file = MINDMAP_DIR / f"mindmap-{mindmap_id}.html"
            if mindmap_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(mindmap_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Mind map not found")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")


if __name__ == "__main__":
    port = 8090
    t = threading.Thread(target=_collect_history, daemon=True)
    t.start()
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Pi Dashboard running at http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
