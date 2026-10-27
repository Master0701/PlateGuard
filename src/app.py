import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from cryptography.fernet import Fernet, InvalidToken
from core import defaults, evaluate, validate_rules, number
from collector import collect, resource

VERSION = '1.0.0'
MAX_BODY = 8 * 1024 * 1024

class Store:
    def __init__(self, folder):
        self.path = folder / 'history.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, node TEXT, at REAL, payload TEXT);
                CREATE INDEX IF NOT EXISTS samples_node_at ON samples(node,at);
                CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, seen REAL, payload TEXT, previous TEXT);
                CREATE TABLE IF NOT EXISTS nonces(id TEXT PRIMARY KEY, at REAL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL, node TEXT, text TEXT);
                CREATE TABLE IF NOT EXISTS inventory(node TEXT, drive TEXT, payload TEXT, PRIMARY KEY(node,drive));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, report, nonce=None):
        now = time.time()
        node = report['node_id']
        with self.connect() as db:
            if nonce:
                db.execute('INSERT INTO nonces VALUES (?,?)', (nonce, now))
            old = db.execute('SELECT payload FROM nodes WHERE id=?', (node,)).fetchone()
            previous = old[0] if old else '{}'
            if old and json.loads(previous)['collected_at'] >= report['collected_at']:
                return False
            payload = json.dumps(report)
            db.execute('INSERT INTO samples(node,at,payload) VALUES (?,?,?)', (node, report['collected_at'], payload))
            db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?)', (node, now, payload, previous))
            for d in report['drives']:
                item = {k:d[k] for k in ('id','model','serial')}
                db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)',(node,d['id'],json.dumps(item)))
            db.execute('DELETE FROM samples WHERE at < ?', (now - 90*86400,))
            db.execute('DELETE FROM nonces WHERE at < ?', (now-600,))
            db.execute('DELETE FROM events WHERE at < ?', (now-90*86400,))
        return True

    def nodes(self):
        with self.connect() as db:
            return [(seen, json.loads(p), json.loads(prev)) for seen,p,prev in db.execute('SELECT seen,payload,previous FROM nodes')]

    def event(self, node, text):
        with self.connect() as db:
            db.execute('INSERT INTO events(at,node,text) VALUES (?,?,?)', (time.time(), node, text))

    def events(self):
        with self.connect() as db:
            return [dict(at=a,node=n,text=t) for a,n,t in db.execute('SELECT at,node,text FROM events ORDER BY id DESC LIMIT 100')]

    def inventory(self, node):
        with self.connect() as db:
            return [json.loads(p) for (p,) in db.execute('SELECT payload FROM inventory WHERE node=?',(node,))]

    def history(self, node, drive):
        with self.connect() as db:
            rows = db.execute('SELECT at,payload FROM samples WHERE node=? ORDER BY at DESC LIMIT 500', (node,)).fetchall()
        return [dict(at=at, metrics=d['metrics']) for at,p in reversed(rows) for d in json.loads(p)['drives'] if d['id'] == drive]

def validate_report(p):
    if not isinstance(p, dict) or not isinstance(p.get('node_id'), str) or not 1 <= len(p['node_id']) <= 100:
        raise ValueError('Ungültige Rechner-ID')
    if not isinstance(p.get('node_name'), str) or len(p['node_name']) > 200:
        raise ValueError('Ungültiger Rechnername')
    if number(p.get('collected_at')) is None or not time.time()-86400 <= p['collected_at'] <= time.time()+120:
        raise ValueError('Messzeit ungültig / Systemuhren prüfen')
    if number(p.get('interval')) is None or not 30 <= p['interval'] <= 86400:
        raise ValueError('Ungültiges Intervall')
    if not isinstance(p.get('messages'), list) or not all(isinstance(m,str) for m in p['messages']):
        raise ValueError('Ungültige Meldungen')
    if not isinstance(p.get('drives'), list) or len(p['drives']) > 256:
        raise ValueError('Ungültige Laufwerke')
    ids = set()
    for d in p['drives']:
        if not isinstance(d, dict) or not isinstance(d.get('id'), str) or d['id'] in ids:
            raise ValueError('Ungültige/mehrfache Laufwerk-ID')
        ids.add(d['id'])
        for key in ('model','serial','device','protocol'):
            if not isinstance(d.get(key), str) or len(d[key]) > 1000:
                raise ValueError('Ungültige Laufwerksdaten')
        if not isinstance(d.get('metrics'),dict) or any(number(v) is None for v in d['metrics'].values()):
            raise ValueError('Ungültige Messwerte')
        if not isinstance(d.get('readable'),bool) or not isinstance(d.get('partial'),bool):
            raise ValueError('Ungültiger Lesestatus')
    return p

class Application:
    def __init__(self, role, folder=None, ui_port=None, api_port=None):
        self.role = role
        self.folder = Path(folder or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PlateGuard' / role)
        self.folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(self.folder/'app.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log_handler = handler
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self.lock = threading.RLock()
        self.config = dict(node_id=str(uuid.uuid4()), node_name=socket.gethostname(), interval=300,
                           offline_after=900, hub_url='', key=Fernet.generate_key().decode() if role == 'hub' else '',
                           notify_yellow=True, notify_red=True, sound=False, rules=defaults(),
                           api_port=api_port or 9766, muted_until=0)
        cfg_path = self.folder/'config.json'
        if cfg_path.exists():
            self.config.update(json.loads(cfg_path.read_text(encoding='utf-8')))
        if api_port:
            self.config['api_port'] = api_port
        self.save_config()
        self.store = Store(self.folder)
        self.ui_token = secrets.token_urlsafe(32)
        self.ui_port = ui_port or (9765 if role == 'hub' else 9767)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.icon = None
        self.servers = []
        self.last_error = ''
        self.delivery = 'Noch keine Übertragung' if role == 'agent' else ''
        self.busy = False
        self.last_alerts = {}
        self.last_notice = {}

    def save_config(self):
        path = self.folder/'config.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, path)

    def settings(self, data):
        with self.lock:
            c = copy.deepcopy(self.config)
            for k in ('node_name','interval','offline_after','hub_url','key','notify_yellow','notify_red','sound','rules'):
                if k in data:
                    c[k] = data[k]
            for k, lo, hi in (('interval',30,86400),('offline_after',60,604800)):
                if type(c[k]) is not int or not lo <= c[k] <= hi:
                    raise ValueError(f'{k}: erlaubt sind {lo} bis {hi} Sekunden.')
            if not isinstance(c['node_name'],str) or not 1 <= len(c['node_name']) <= 200:
                raise ValueError('Rechnername erforderlich (max. 200 Zeichen).')
            for k in ('notify_yellow','notify_red','sound'):
                if type(c[k]) is not bool:
                    raise ValueError('Ungültige Alarm-Einstellung')
            validate_rules(c['rules'])
            if not isinstance(c['key'],str):
                raise ValueError('Ungültiger Verbindungsschlüssel')
            if c['key']:
                try:
                    Fernet(c['key'].encode('ascii'))
                except Exception:
                    raise ValueError('Verbindungsschlüssel muss aus der Zentrale kopiert werden.')
            if self.role == 'hub' and not c['key']:
                raise ValueError('Zentrale benötigt einen Verbindungsschlüssel.')
            if c['hub_url']:
                u = urllib.parse.urlsplit(c['hub_url'])
                if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
                    raise ValueError('Adresse z.B. http://192.168.1.20:9766 ohne Pfad eingeben.')
            self.config = c
            self.save_config()
        self.wake.set()

    def state(self):
        with self.lock:
            cfg = copy.deepcopy(self.config)
        nodes = []
        for seen, report, prev in self.store.nodes():
            old = {d['id']: d for d in prev.get('drives', [])}
            node = copy.deepcopy(report)
            node['seen'] = seen
            age = time.time()-report['collected_at']
            node['offline'] = time.time()-seen > max(cfg['offline_after'], report['interval']*3)
            node['stale'] = age > max(cfg['offline_after'], report['interval']*3)
            for drive in node['drives']:
                drive.update(evaluate(drive, old.get(drive['id']), cfg['rules']))
                drive.pop('raw', None)
            current = {d['id'] for d in node['drives']}
            node['missing'] = [d for d in self.store.inventory(node['node_id']) if d['id'] not in current]
            nodes.append(node)
        return dict(role=self.role, version=VERSION, config=cfg, nodes=nodes, events=self.store.events(),
                    error=self.last_error, delivery=self.delivery, busy=self.busy, folder=str(self.folder),
                    api_port=cfg['api_port'], ui_port=self.ui_port)

    def alarms(self):
        cfg = self.config
        for node in self.state()['nodes']:
            if node['offline'] or node['stale']:
                continue
            for drive in node['drives']:
                identity = node['node_id'] + '/' + drive['id']
                sig = tuple(sorted((a['metric'],a['level']) for a in drive['alerts']))
                previous = self.last_alerts.get(identity)
                self.last_alerts[identity] = sig
                if not sig or sig == previous:
                    continue
                text = f"{node['node_name']} · {drive['model']}: " + ', '.join(a['label'] for a in drive['alerts'])
                self.store.event(node['node_name'], text)
                level = drive['level']
                if cfg.get('muted_until',0) > time.time() or not cfg.get('notify_'+level,False):
                    continue
                if time.time()-self.last_notice.get(identity,0) < 60:
                    continue
                self.last_notice[identity] = time.time()
                if self.icon:
                    self.icon.notify(text[:240], 'PlateGuard – '+ ('ROT' if level == 'red' else 'GELB'))
                    if cfg['sound'] and os.name == 'nt':
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    def deliver(self, report):
        cfg = self.config.copy()
        if not cfg['hub_url'] or not cfg['key']:
            self.delivery = 'Noch nicht verbunden – Zentrale und Schlüssel in Einstellungen eintragen.'
            return
        envelope = dict(nonce=secrets.token_hex(24), report=report)
        data = Fernet(cfg['key'].encode()).encrypt(json.dumps(envelope).encode())
        request = urllib.request.Request(cfg['hub_url'].rstrip('/')+'/api/v1/report', data=data,
                                         headers={'Content-Type':'application/octet-stream'}, method='POST')
        try:
            # Do not forward ciphertext to unexpected redirects; no OS HTTP proxy for LAN telemetry.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=12) as response:
                if response.status != 200:
                    raise RuntimeError('HTTP '+str(response.status))
            self.delivery = 'Übertragen: '+time.strftime('%H:%M:%S')
        except Exception as ex:
            self.delivery = 'Zentrale nicht erreichbar / Verbindung prüfen: '+str(ex)[:160]

    def worker(self):
        while not self.stop.is_set():
            if self.role == 'agent':
                self.busy = True
                try:
                    report = collect()
                    report.update(node_id=self.config['node_id'], node_name=self.config['node_name'], interval=self.config['interval'])
                    self.store.save(report)
                    self.last_error = ''
                    self.deliver(report)
                except Exception as ex:
                    logging.exception('Abfrage fehlgeschlagen')
                    self.last_error = 'Abfrage fehlgeschlagen: '+str(ex)
                finally:
                    self.busy = False
            try:
                self.alarms()
            except Exception:
                logging.exception('Alarm-Auswertung fehlgeschlagen')
            self.wake.wait(self.config['interval'] if self.role == 'agent' else 5)
            self.wake.clear()

    def ingest(self, body):
        try:
            payload = Fernet(self.config['key'].encode()).decrypt(body, ttl=300)
            envelope = json.loads(payload)
            nonce = envelope['nonce']
            if not isinstance(nonce,str) or len(nonce) != 48:
                raise ValueError('Ungültige Nachrichten-ID')
            report = validate_report(envelope['report'])
            self.store.save(report, nonce)
        except (InvalidToken, KeyError, ValueError, TypeError, sqlite3.IntegrityError):
            raise ValueError('Nachricht ungültig, abgelaufen oder bereits empfangen.')

    def start_server(self, host, port, remote=False):
        app = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            def setup(self):
                super().setup()
                self.connection.settimeout(10)
            def log_message(self, *args):
                pass
            def reply(self, code, payload, content='application/json; charset=utf-8'):
                body = payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header('Content-Type',content)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
            def authorized(self):
                return secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+app.ui_token)
            def do_GET(self):
                if remote:
                    return self.reply(404,dict(error='Not found'))
                if self.headers.get('Host') != f'127.0.0.1:{app.ui_port}':
                    return self.reply(403,dict(error='Ungültiger Host'))
                path = urllib.parse.urlsplit(self.path)
                static = {'/':'web/index.html','/app.js':'web/app.js','/style.css':'web/style.css'}
                if path.path in static:
                    mime = 'text/html; charset=utf-8' if path.path == '/' else 'text/javascript; charset=utf-8' if path.path.endswith('js') else 'text/css; charset=utf-8'
                    return self.reply(200,resource(static[path.path]).read_bytes(),mime)
                if not self.authorized():
                    return self.reply(401,dict(error='Über das Tray-Menü öffnen.'))
                if path.path == '/api/state':
                    return self.reply(200,app.state())
                if path.path == '/api/history':
                    q = urllib.parse.parse_qs(path.query)
                    return self.reply(200,app.store.history(q.get('node',[''])[0],q.get('drive',[''])[0]))
                if path.path == '/api/licenses':
                    return self.reply(200,resource('LICENSES.txt').read_bytes(),'text/plain; charset=utf-8')
                if path.path == '/api/smartmontools-source':
                    return self.reply(200,resource('vendor/smartmontools-7.5.tar.gz').read_bytes(),'application/gzip')
                return self.reply(404,{})
            def do_POST(self):
                try:
                    if remote:
                        if self.path != '/api/v1/report':
                            return self.reply(404,{})
                    elif not self.authorized() or self.headers.get('Host') != f'127.0.0.1:{app.ui_port}':
                        return self.reply(401,dict(error='Nicht autorisiert'))
                    length = int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= MAX_BODY:
                        return self.reply(413,dict(error='Nachricht zu groß/leer'))
                    body = self.rfile.read(length)
                    if remote:
                        app.ingest(body)
                    else:
                        data = json.loads(body)
                        if self.path == '/api/settings':
                            app.settings(data)
                        elif self.path == '/api/poll':
                            app.wake.set()
                        elif self.path == '/api/mute':
                            with app.lock:
                                app.config['muted_until'] = time.time()+3600 if data.get('muted') else 0
                                app.save_config()
                        else:
                            return self.reply(404,{})
                    self.reply(200,dict(ok=True))
                except (ValueError, TypeError, KeyError) as ex:
                    self.reply(400,dict(error=str(ex)))
                except Exception:
                    logging.exception('API-Fehler')
                    self.reply(500,dict(error='Interner Fehler, siehe lokales Protokoll.'))
        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = False
            request_queue_size = 32
            def __init__(self,*args):
                self.slots = threading.BoundedSemaphore(16)
                super().__init__(*args)
            def process_request(self,request,address):
                if not self.slots.acquire(blocking=False):
                    request.close()
                    return
                try:
                    super().process_request(request,address)
                except Exception:
                    self.slots.release()
                    raise
            def process_request_thread(self,request,address):
                try:
                    super().process_request_thread(request,address)
                finally:
                    self.slots.release()
        server = Server((host,port),Handler)
        self.servers.append(server)
        threading.Thread(target=server.serve_forever,daemon=True).start()

    def open(self, page='dashboard'):
        webbrowser.open(f'http://127.0.0.1:{self.ui_port}/#token={self.ui_token}&page={page}')

    def quit(self, *args):
        self.stop.set()
        self.wake.set()
        for server in self.servers:
            server.shutdown()
        if self.icon:
            self.icon.stop()
        logging.getLogger().removeHandler(self.log_handler)
        self.log_handler.close()

    def run(self, headless=False):
        self.start_server('127.0.0.1',self.ui_port)
        if self.role == 'hub':
            self.start_server('0.0.0.0',self.config['api_port'],True)
        if not headless:
            import pystray
            from PIL import Image, ImageDraw
            image = Image.new('RGBA',(64,64),(0,0,0,0))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((6,5,58,59),radius=12,fill='#112c33',outline='#5ee0b5',width=4)
            draw.ellipse((23,19,43,39),outline='#5ee0b5',width=4)
            draw.line((33,29,47,44),fill='white',width=4)
            self.icon = pystray.Icon('PlateGuard-'+self.role,image,'PlateGuard '+('Zentrale' if self.role=='hub' else 'Agent'),
                menu=pystray.Menu(
                    pystray.MenuItem('Übersicht öffnen',lambda:self.open(),default=True),
                    pystray.MenuItem('Einstellungen',lambda:self.open('settings')),
                    pystray.MenuItem('Jetzt abfragen / aktualisieren',lambda:self.wake.set()),
                    pystray.MenuItem('Alarme 1 Stunde pausieren',lambda:self.mute()),
                    pystray.MenuItem('Alarme wieder aktivieren',lambda:self.mute(False)),
                    pystray.MenuItem('Beenden',self.quit)))
        threading.Thread(target=self.worker,daemon=True).start()
        if headless:
            self.stop.wait()
        else:
            self.icon.run()

    def mute(self, enabled=True):
        with self.lock:
            self.config['muted_until'] = time.time()+3600 if enabled else 0
            self.save_config()

def main(role):
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('--ui-port',type=int)
    parser.add_argument('--api-port',type=int)
    parser.add_argument('--smoke-test',action='store_true')
    args = parser.parse_args()
    if args.smoke_test:
        # Executable self-check without opening listeners, touching drives, or showing UI.
        from collector import smartctl
        result = {'version':VERSION,'role':role,'web':resource('web/index.html').exists(),
                  'crypto':bool(Fernet.generate_key()),'smartctl':smartctl(['--version']).get('smartctl',{}).get('version')}
        Path(args.data_dir or '.').mkdir(parents=True,exist_ok=True)
        (Path(args.data_dir or '.')/f'{role}-smoke.json').write_text(json.dumps(result))
        return
    mutex = None
    try:
        if os.name == 'nt' and not args.headless:
            import ctypes
            kernel = ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateMutexW.restype = ctypes.c_void_p
            mutex = kernel.CreateMutexW(None,False,'Local\\PlateGuard-'+role)
            if ctypes.get_last_error() == 183:
                ctypes.windll.user32.MessageBoxW(0,'PlateGuard läuft bereits. Bitte über das Tray-Symbol öffnen.','PlateGuard',0)
                return
        Application(role,args.data_dir,args.ui_port,args.api_port).run(args.headless)
    except Exception as ex:
        logging.exception('Start fehlgeschlagen')
        if os.name == 'nt' and not args.headless:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(ex),'PlateGuard – Start fehlgeschlagen',16)
        else:
            raise
