"""Reproducible local build inputs, two standalone Windows executables."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
exe=ROOT/'vendor/smartmontools/bin/smartctl.exe'
expected='b5db94e5082c042be44994b7a4fa8f7b5c8e713b2ab1c9a560d8f7a7995ea27d'
if hashlib.sha256(exe.read_bytes()).hexdigest()!=expected:
    raise SystemExit('smartctl-Prüfsumme stimmt nicht überein')
licenses=['PlateGuard 1.0.0 – Drittanbieter-Komponenten\n\nsmartmontools 7.5\n'+(ROOT/'vendor/smartmontools/doc/COPYING.txt').read_text()]
for name in ['pystray','Pillow','cryptography','cffi','pycparser','six','pyinstaller']:
    dist=importlib.metadata.distribution(name)
    licenses.append('\n\n=== '+name+' '+dist.version+' ===\n')
    for f in dist.files or []:
        if ('license' in str(f).lower() or 'copying' in str(f).lower()) and dist.locate_file(f).is_file():
            licenses.append(dist.locate_file(f).read_text(encoding='utf-8',errors='replace'))
licenses.append('\n\n=== Python ===\n'+Path(sys.base_prefix,'LICENSE.txt').read_text(encoding='utf-8'))
(ROOT/'LICENSES.txt').write_text('\n'.join(licenses),encoding='utf-8')
for role,label in [('hub','Zentrale'),('agent','Agent')]:
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
          '--name','PlateGuard-'+label,'--paths','src',
          '--add-data','web;web','--add-data','LICENSES.txt;.',
          '--add-data','vendor/smartmontools-7.5.tar.gz;vendor',
          '--add-data','vendor/smartmontools/bin/drivedb.h;vendor/smartmontools/bin',
          '--add-binary','vendor/smartmontools/bin/smartctl.exe;vendor/smartmontools/bin']
    if role=='agent':args+=['--uac-admin']
    subprocess.run(args+['src/'+role+'.py'],cwd=ROOT,check=True)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'dist').glob('*.exe')}
(ROOT/'dist/SHA256.json').write_text(json.dumps(manifest,indent=2))
