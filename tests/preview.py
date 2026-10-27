"""Explicitly synthetic data for local UI verification only."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Application
from core import normalize
app=Application('hub',Path(__file__).resolve().parents[1]/'build/preview-data',ui_port=19865,api_port=19866)
for i in range(12):
    drives=[]
    for model,serial,temp,attrs in [('DEMO · NAS IronWolf 8 TB','DEMO-001',38,{5:0,197:0,198:0}),('DEMO · Archiv HDD 4 TB','DEMO-002',44,{5:12,197:2,198:0})]:
        drives.append(normalize(dict(model_name=model,serial_number=serial,device={'protocol':'ATA'},temperature={'current':temp+i%3},user_capacity={'bytes':8_000_000_000_000},smart_status={'passed':True},ata_smart_attributes={'table':[{'id':k,'name':'Test attribute','value':100,'worst':100,'thresh':10,'raw':{'value':v}} for k,v in attrs.items()]}),{'name':'/dev/'+serial,'type':'sat'}))
    app.store.save(dict(node_id='demo-pc',node_name='DEMO · Archiv-PC',interval=300,collected_at=time.time()-3300+i*300,drives=drives,messages=[]))
app.start_server('127.0.0.1',19865)
(Path(__file__).resolve().parents[1]/'build/preview-url.txt').write_text('http://127.0.0.1:19865/#token='+app.ui_token)
app.stop.wait()
