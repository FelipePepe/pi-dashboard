Your job is to extend the Pi Dashboard (server.py + index.html) with three new features:

## 1. Alerts system
In server.py, add configurable thresholds:
- CPU > 85% → alert
- RAM > 80% → alert  
- Temp > 70°C → alert
- Disk > 90% → alert

Add GET /api/alerts that returns active alerts as a list of {level: "warning"|"critical", metric, value, threshold, message}.

In index.html, show a red alert banner at the top of every tab when there are active alerts. Auto-refresh every 5s.

## 2. System logs tab
Add GET /api/logs in server.py that runs `journalctl -n 100 --no-pager -o short` and returns lines as JSON array.

Add a "📋 Logs" tab in index.html showing the last 100 log lines in a dark scrollable terminal-style box. Auto-refresh every 10s. Lines with "error" or "fail" highlighted in red, "warn" in yellow.

## 3. Subagents panel tab
Add GET /api/subagents in server.py that reads /home/felipe/.openclaw/agents/main/sessions/sessions.json and returns active/recent sessions with their label, status, last activity.

Add a "🤖 Agentes" tab in index.html showing the sessions as cards with name, status dot, and last activity time.

Keep everything in server.py and index.html. Make a commit after each feature.

When completely finished, run:
openclaw system event --text "Done: Alerts, Logs and Subagents panel added to Pi dashboard" --mode now
