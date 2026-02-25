Your job is to extend the Pi Dashboard (server.py + index.html) with a systemd services monitor tab.

Add:
1. In server.py: a new endpoint GET /api/services that runs `systemctl list-units --type=service --state=running,failed,inactive --no-pager --plain` and parses the output returning a list of { name, load, active, sub, description }
   - Also include specifically: openclaw, engram, ssh, if they exist
2. In index.html: a new "⚙️ Servicios" tab showing:
   - Green dot for running, red for failed, gray for inactive
   - Service name + description
   - Refresh every 10s

Keep everything in server.py and index.html. Make a commit after every change.

When completely finished, run:
openclaw system event --text "Done: Services monitor tab added to Pi dashboard" --mode now
