# Google Tasks Sync for GNOME Calendar & Desktop Widgets

This tool synchronizes tasks from **Google Tasks** (via GNOME Online Accounts / Evolution Data Server) into a dedicated local calendar named **"Tarefas do Google"**.

## Why this is needed
Google's CalDAV endpoint natively exposes calendar events (`VEVENT`), but excludes Google Tasks (`VTODO`). GNOME Calendar and `gnome-shell-calendar-server` only query EDS calendar sources.

This tool extracts the cached tasks from Evolution Data Server's SQLite cache, mirrors them as calendar events (`VEVENT`), and updates the local calendar automatically with full details (timestamps, completion markers, descriptions, and account info).

## Installation

1. Copy the sync script:
   ```bash
   cp sync-google-tasks.py ~/.local/bin/
   chmod +x ~/.local/bin/sync-google-tasks.py
   ```

2. Copy the systemd user service and timer:
   ```bash
   cp google-tasks-sync.service google-tasks-sync.timer ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now google-tasks-sync.timer
   ```

3. Run the initial sync:
   ```bash
   ~/.local/bin/sync-google-tasks.py
   ```
