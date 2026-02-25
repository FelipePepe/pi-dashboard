#!/usr/bin/env python3
"""Pi Dashboard server - exposes /api/stats, /api/memory and serves index.html on port 8080."""

import json
import os
import sqlite3
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

ENGRAM_DB = os.path.expanduser("~/.engram/engram.db")


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
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")


if __name__ == "__main__":
    port = 8080
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Pi Dashboard running at http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
