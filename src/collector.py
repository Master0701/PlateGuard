import json
import os
from pathlib import Path
import subprocess
import sys
import time
from core import normalize

def resource(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return root / name

def smartctl(args):
    exe = resource('vendor/smartmontools/bin/smartctl.exe')
    p = subprocess.run([str(exe), '-j', *args], capture_output=True, timeout=45,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # smartctl returns health/error bit flags, NOT a conventional success/failure code.
    try:
        data = json.loads(p.stdout.decode('utf-8', errors='replace'))
    except (ValueError, UnicodeError):
        raise RuntimeError('smartctl lieferte keine JSON-Daten: ' + p.stderr.decode(errors='replace')[:300])
    return data

def collect():
    start = time.time()
    scan = smartctl(['--scan-open'])
    messages = [m.get('string', '') for m in scan.get('smartctl', {}).get('messages', [])]
    devices = scan.get('devices', [])
    drives = []
    seen = set()
    for device in devices:
        try:
            data = smartctl(['-x', '-d', device['type'], device['name']])
            drive = normalize(data, device)
        except Exception as ex:
            drive = normalize({}, device)
            drive['messages'] = [str(ex)]
        if drive['id'] not in seen:
            drives.append(drive)
            seen.add(drive['id'])
    if not devices:
        messages.append('Keine SMART-Geräte gefunden. Administratorrechte, USB-Bridge oder RAID-Unterstützung prüfen.')
    return dict(drives=drives, collected_at=time.time(), duration=round(time.time()-start, 1), messages=messages)
