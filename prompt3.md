Your job is to extend the Pi Dashboard (server.py + index.html) with historical charts for CPU and RAM.

Currently the dashboard refreshes stats every 5s but doesn't store history.

Add:
1. In server.py: an in-memory circular buffer (last 60 data points = 5 minutes) that records cpu_percent and ram percent every 5s in a background thread
2. A new endpoint GET /api/history that returns the last 60 data points as JSON arrays: { timestamps: [...], cpu: [...], ram: [...] }
3. In index.html: a new "📈 Gráficas" tab with two line charts (CPU % and RAM %) using Chart.js (load from CDN)
   - Charts auto-update every 5s
   - Dark theme, clean lines, no grid clutter

Keep everything in server.py and index.html. Make a commit after every change.

When completely finished, run:
openclaw system event --text "Done: Historical charts added to Pi dashboard" --mode now
