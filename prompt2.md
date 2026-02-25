Your job is to extend the existing Pi Dashboard (server.py + index.html) to include an Engram memory viewer tab.

The dashboard already has a /api/stats endpoint and an index.html with dark theme.

Add:

1. A new tab "🧠 Memoria" in the existing index.html navigation
2. A new API endpoint GET /api/memory in server.py that reads from SQLite at /home/felipe/.engram/engram.db and returns:
   - List of observations (id, type, title, content, project, created_at) ordered by created_at DESC
   - A search parameter ?q= for filtering by title/content
3. In the Memoria tab:
   - A search input box that filters live as you type
   - Color-coded badges per type (session=blue, preference=green, others=gray)
   - Each entry shows: badge, title, date, and expandable content on click
   - Same dark theme as the rest of the dashboard

Keep everything in the same two files (server.py and index.html). No new dependencies beyond what's already used (stdlib + psutil).

Make a commit after every significant change.

When completely finished, run:
openclaw system event --text "Done: Engram memory viewer integrated in Pi dashboard" --mode now
