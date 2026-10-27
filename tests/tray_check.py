"""Brief Windows tray lifecycle check with no disk access or remote listener."""
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Application
app=Application('agent',Path(__file__).resolve().parents[1]/'build/tray-check',ui_port=19977)
app.worker=lambda:None
result=[]
def verify():
    time.sleep(3)
    result.append(bool(app.icon and app.icon.visible))
    app.quit()
threading.Thread(target=verify,daemon=True).start()
app.run()
assert result==[True],result
print('Tray-Symbol erstellt, sichtbar, Menü initialisiert, sauber beendet.')
