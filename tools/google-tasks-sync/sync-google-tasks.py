#!/usr/bin/env python3
"""
Sync Google Tasks into GNOME Calendar and Desktop Widgets.

Extracts Google Tasks (cached locally by Evolution Data Server / GNOME Online Accounts)
and creates mirror calendar events in a local EDS calendar named "Tarefas do Google".
This allows GNOME Calendar, GNOME Shell top panel, and Desktop Widgets to display
all tasks, reminders, and appointments seamlessly.
"""

import os
import sys
import glob
import sqlite3
import datetime
import re
import subprocess
import ctypes
from ctypes import c_void_p, c_char_p, POINTER, Structure

CALENDAR_ICS_PATH = os.path.expanduser('~/.local/share/evolution/calendar/google-tasks/calendar.ics')
SOURCES_DIR = os.path.expanduser('~/.config/evolution/sources')

def discover_task_sources():
    """Discover task list sources dynamically via EDS registry or cache directory fallback."""
    sources = {}
    try:
        class GList(Structure):
            pass
        GList._fields_ = [('data', c_void_p), ('next', POINTER(GList)), ('prev', POINTER(GList))]

        eds = ctypes.CDLL('libedataserver-1.2.so.27')
        eds.e_source_registry_new_sync.restype = c_void_p
        eds.e_source_registry_new_sync.argtypes = [c_void_p, c_void_p]
        eds.e_source_registry_list_sources.restype = POINTER(GList)
        eds.e_source_registry_list_sources.argtypes = [c_void_p, c_char_p]
        eds.e_source_registry_ref_source.restype = c_void_p
        eds.e_source_registry_ref_source.argtypes = [c_void_p, c_char_p]
        eds.e_source_get_uid.restype = c_char_p
        eds.e_source_get_uid.argtypes = [c_void_p]
        eds.e_source_get_display_name.restype = c_char_p
        eds.e_source_get_display_name.argtypes = [c_void_p]
        eds.e_source_get_parent.restype = c_char_p
        eds.e_source_get_parent.argtypes = [c_void_p]

        registry = eds.e_source_registry_new_sync(None, None)
        g_sources = eds.e_source_registry_list_sources(registry, b'Task List')
        curr = g_sources
        while curr:
            src = curr.contents.data
            uid = eds.e_source_get_uid(src).decode()
            name = eds.e_source_get_display_name(src).decode()
            parent_uid = eds.e_source_get_parent(src)
            account_name = ''
            if parent_uid:
                parent_src = eds.e_source_registry_ref_source(registry, parent_uid)
                if parent_src:
                    account_name = eds.e_source_get_display_name(parent_src).decode()
            # Only track Google Tasks (or remote accounts), skip local personal task list
            if uid != 'system-task-list':
                sources[uid] = {'name': name, 'account': account_name}
            curr = curr.contents.next
    except Exception as e:
        # Fallback to cache directory inspection
        pass

    # Ensure all existing task cache databases are covered
    for path in glob.glob(os.path.expanduser('~/.cache/evolution/tasks/*/cache.db')):
        folder_uid = os.path.basename(os.path.dirname(path))
        if folder_uid != 'trash' and folder_uid not in sources:
            sources[folder_uid] = {'name': 'Minhas tarefas', 'account': 'Google'}

    return sources

def next_day_str(d_str):
    """Return YYYYMMDD string for the day following the input date."""
    try:
        dt = datetime.datetime.strptime(d_str[:8], '%Y%m%d').date()
        return (dt + datetime.timedelta(days=1)).strftime('%Y%m%d')
    except Exception:
        return d_str

def escape_ical(text):
    """Escape text for iCalendar properties."""
    if not text:
        return ''
    t = text.replace('\\', '\\\\').replace(';', r'\;').replace(',', r'\,')
    t = t.replace('\r\n', r'\n').replace('\n', r'\n')
    return t

def parse_vtodo(obj, default_summary, default_desc):
    """Parse unfolded VTODO data to preserve Unicode summary, description, and timestamps."""
    if not obj:
        return default_summary or '', default_desc or '', None, None

    unfolded = re.sub(r'\r?\n[ \t]', '', obj)
    summary = default_summary
    desc = default_desc
    created = None
    last_mod = None

    for line in unfolded.splitlines():
        if line.startswith('SUMMARY:'):
            summary = line[8:].replace(r'\,', ',').replace(r'\;', ';').replace(r'\\', '\\')
        elif line.startswith('DESCRIPTION:'):
            desc = line[12:].replace(r'\,', ',').replace(r'\;', ';').replace(r'\n', '\n').replace(r'\\', '\\')
        elif line.startswith('CREATED:'):
            created = line[8:].strip()
        elif line.startswith('LAST-MODIFIED:'):
            last_mod = line[14:].strip()

    return summary or default_summary or '', desc or default_desc or '', created, last_mod

def build_calendar_ics(sources):
    """Extract tasks from SQLite databases and generate an iCalendar string."""
    today = datetime.date.today()
    today_str = today.strftime('%Y%m%d')
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.strftime('%Y%m%dT%H%M%SZ')

    vevents = []

    for uid, meta in sources.items():
        db_path = os.path.expanduser(f'~/.cache/evolution/tasks/{uid}/cache.db')
        if not os.path.exists(db_path):
            continue

        try:
            conn = sqlite3.connect(db_path, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT ECacheUID, status, due, completed, summary, description, ECacheOBJ FROM ECacheObjects;")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"Warning: could not read {db_path}: {e}", file=sys.stderr)
            continue

        list_name = meta.get('name', 'Tarefas')
        account_name = meta.get('account', '')

        for tid, status, due, completed, sm, ds, obj in rows:
            is_completed = (status == 'completed')
            full_summary, full_desc, created, last_mod = parse_vtodo(obj, sm, ds)

            if due and len(due) >= 8:
                start_date = due[:8]
            elif is_completed and completed and len(completed) >= 8:
                start_date = completed[:8]
            else:
                # Active task with no due date -> display on today's agenda
                start_date = today_str

            end_date = next_day_str(start_date)
            prefix = '✓ [Tarefa] ' if is_completed else '[Tarefa] '
            event_summary = prefix + (full_summary or 'Sem título')

            info_lines = []
            if full_desc and full_desc.strip():
                info_lines.append(full_desc.strip())
                info_lines.append('')
            if account_name:
                info_lines.append(f"Conta: {account_name}")
            info_lines.append(f"Lista: {list_name}")
            info_lines.append(f"Status: {'Concluída' if is_completed else 'Pendente'}")
            if completed and len(completed) >= 8:
                c_d = completed[:8]
                info_lines.append(f"Concluída em: {c_d[6:8]}/{c_d[4:6]}/{c_d[:4]}")

            event_desc = escape_ical('\n'.join(info_lines))
            esc_summary = escape_ical(event_summary)
            c_stamp = created or now_iso
            m_stamp = last_mod or now_iso

            vevent = (
                f"BEGIN:VEVENT\n"
                f"UID:google-task-{tid}\n"
                f"DTSTAMP:{now_iso}\n"
                f"CREATED:{c_stamp}\n"
                f"LAST-MODIFIED:{m_stamp}\n"
                f"SUMMARY:{esc_summary}\n"
                f"DESCRIPTION:{event_desc}\n"
                f"DTSTART;VALUE=DATE:{start_date}\n"
                f"DTEND;VALUE=DATE:{end_date}\n"
                f"STATUS:CONFIRMED\n"
                f"CATEGORIES:Tarefa,Google Tasks\n"
                f"TRANSP:TRANSPARENT\n"
                f"END:VEVENT"
            )
            vevents.append(vevent)

    # Sort events by summary for deterministic output
    vevents.sort()

    content = (
        f"BEGIN:VCALENDAR\n"
        f"CALSCALE:GREGORIAN\n"
        f"PRODID:-//Google Tasks Sync for GNOME//EN\n"
        f"VERSION:2.0\n"
        f"X-EVOLUTION-DATA-REVISION:{now_iso}(tasks)\n"
        + '\n'.join(vevents)
        + "\nEND:VCALENDAR\n"
    )

    return content, len(vevents)

def main():
    sources = discover_task_sources()
    content, total_tasks = build_calendar_ics(sources)

    os.makedirs(os.path.dirname(CALENDAR_ICS_PATH), exist_ok=True)

    # Compare content ignoring DTSTAMP and X-EVOLUTION-DATA-REVISION to avoid unnecessary reloads
    strip_re = re.compile(r'^(DTSTAMP|X-EVOLUTION-DATA-REVISION):.*$', re.MULTILINE)
    current_content = ''
    if os.path.exists(CALENDAR_ICS_PATH):
        try:
            with open(CALENDAR_ICS_PATH, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception:
            pass

    if strip_re.sub('', current_content) == strip_re.sub('', content):
        # Already up to date
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Google Tasks sync: already up-to-date ({total_tasks} tasks).")
        return

    # Write atomically
    tmp_path = CALENDAR_ICS_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp_path, CALENDAR_ICS_PATH)

    # Restart calendar factory and calendar server so changes are immediately visible
    try:
        subprocess.run(['systemctl', '--user', 'restart', 'evolution-calendar-factory'], check=False)
        subprocess.run(['killall', 'gnome-shell-calendar-server'], check=False)
    except Exception:
        pass

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Google Tasks sync: synchronized {total_tasks} tasks.")

if __name__ == '__main__':
    main()
