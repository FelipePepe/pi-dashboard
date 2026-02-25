Your job is to build a local web dashboard for a ClockworkPi running Ubuntu ARM64.

The dashboard should be a single HTML file (index.html) with a Python backend (server.py using Flask or http.server).

It should show in real-time (auto-refresh every 5s via JS):
- CPU usage %
- RAM usage %
- Disk usage %
- CPU temperature (read from /sys/class/thermal/thermal_zone0/temp)
- System load average
- Uptime
- Top 5 processes by CPU

Design: dark theme, clean, minimal. No external dependencies — everything inline (CSS, JS).

The Python server exposes a /api/stats JSON endpoint and serves index.html on port 8080.

Make a commit after every significant change.

Keep a TODO.md with your progress.

When completely finished, run:
openclaw system event --text "Done: Pi dashboard built and ready at port 8080" --mode now
