# Pi Dashboard - TODO

## Project
Build a local web dashboard for ClockworkPi (Ubuntu ARM64) that shows system stats in real-time.

## Tasks

- [x] Create TODO.md
- [ ] Write server.py (Flask, /api/stats endpoint, port 8080)
- [ ] Write index.html (dark theme, inline CSS/JS, auto-refresh every 5s)
- [ ] Test locally
- [ ] Final commit

## Stats to Display

- CPU usage %
- RAM usage %
- Disk usage %
- CPU temperature (/sys/class/thermal/thermal_zone0/temp)
- System load average
- Uptime
- Top 5 processes by CPU

## Notes

- No external dependencies (all CSS/JS inline)
- Dark theme, clean, minimal design
- Port 8080
