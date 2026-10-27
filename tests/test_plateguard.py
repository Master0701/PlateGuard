import copy
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import normalize,evaluate,defaults,validate_rules
from app import Application,Store,validate_report
from cryptography.fernet import Fernet

def drive(attrs=None, nvme=None, status=True):
    data = dict(model_name='Testdisk',serial_number='123',smart_status=dict(passed=status),smartctl=dict(exit_status=0))
    if attrs is not None:
        data['ata_smart_attributes']={'table':[dict(id=k,raw=dict(value=v)) for k,v in attrs.items()]}
    if nvme is not None:
        data['nvme_smart_health_information_log']=nvme
    return normalize(data,dict(name='/dev/sda',type='sat'))

def report(d=None):
    return dict(node_id='test',node_name='Test-PC',interval=300,collected_at=time.time(),drives=[d or drive({197:0})],messages=[])

class RulesTest(unittest.TestCase):
    def test_pending_sector_is_red(self):
        self.assertEqual(evaluate(drive({197:1}),None,defaults())['level'],'red')
    def test_reallocated_is_yellow(self):
        self.assertEqual(evaluate(drive({5:1}),None,defaults())['level'],'yellow')
    def test_unknown_is_not_green(self):
        self.assertEqual(evaluate(normalize({},dict(name='x')),None,defaults())['level'],'unknown')
    def test_nvme_critical_and_spare(self):
        for n in [dict(critical_warning=4),dict(available_spare=5,available_spare_threshold=10),dict(media_errors=1)]:
            self.assertEqual(evaluate(drive(nvme=n),None,defaults())['level'],'red')
    def test_wear_yellow_then_red(self):
        self.assertEqual(evaluate(drive(nvme={'percentage_used':80}),None,defaults())['level'],'yellow')
        self.assertEqual(evaluate(drive(nvme={'percentage_used':100}),None,defaults())['level'],'red')
    def test_crc_delta_first_reset_unchanged(self):
        d=drive({199:10})
        for prev in (None,drive({199:10}),drive({199:20})):
            self.assertEqual(evaluate(d,prev,defaults())['level'],'green')
        self.assertEqual(evaluate(d,drive({199:9}),defaults())['level'],'yellow')
    def test_partial_retains_health_alert(self):
        d=drive({197:2});d['partial']=True
        self.assertEqual(evaluate(d,None,defaults())['level'],'red')
        d=drive({197:0});d['partial']=True
        self.assertEqual(evaluate(d,None,defaults())['level'],'unknown')
    def test_rule_disable_scope_and_threshold(self):
        r=defaults();r[5]['enabled']=False
        self.assertEqual(evaluate(drive({197:1}),None,r)['level'],'green')
        r[5]['enabled']=True;r[5]['drive']='another-drive'
        self.assertEqual(evaluate(drive({197:1}),None,r)['level'],'green')
    def test_invalid_rules_rejected(self):
        for val in (float('nan'),float('inf'),'oops'):
            r=defaults();r[0]['red']=val
            with self.assertRaises(ValueError):validate_rules(r)
        r=defaults();r[0]['yellow']=2;r[0]['red']=1
        with self.assertRaises(ValueError):validate_rules(r)
    def test_sas(self):
        d=normalize({'scsi_grown_defect_list':3,'scsi_error_counter_log':{'read':{'total_uncorrected_errors':1}}},{'name':'/dev/sdb'})
        self.assertEqual(evaluate(d,None,defaults())['level'],'red')
    def test_sata_ssd_vendor_decoded_wear(self):
        d=normalize({'endurance_used':{'current_percent':91},'smart_status':{'passed':True}},{'name':'x'})
        self.assertEqual(d['metrics']['percentage_used'],91)
        self.assertEqual(evaluate(d,None,defaults())['level'],'yellow')
    def test_nvme_individual_warning_bits(self):
        d=drive(nvme={'critical_warning':12})
        self.assertEqual(d['metrics']['nvme_warning_read_only'],1)
        self.assertEqual(d['metrics']['nvme_warning_reliability'],1)
        self.assertEqual(d['metrics']['nvme_warning_temperature'],0)
    def test_smart_failure_exit_bits_not_discarded(self):
        d=normalize({'smart_status':{'passed':False},'smartctl':{'exit_status':8}},{'name':'x'})
        self.assertTrue(d['readable']);self.assertFalse(d['partial'])
        self.assertEqual(evaluate(d,None,defaults())['level'],'red')

class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Application('hub',self.tmp.name,ui_port=19765,api_port=19766)
    def tearDown(self):
        self.app.quit()
        for s in self.app.servers:s.server_close()
        self.tmp.cleanup()
    def envelope(self,p,key=None,nonce=None):
        return Fernet(key or self.app.config['key'].encode()).encrypt(json.dumps(dict(report=p,nonce=nonce or secrets.token_hex(24))).encode())
    def test_encrypted_ingest_replay_and_wrong_key(self):
        p=report();token=self.envelope(p)
        self.app.ingest(token)
        self.assertEqual(len(self.app.state()['nodes']),1)
        with self.assertRaises(ValueError):self.app.ingest(token)
        with self.assertRaises(ValueError):self.app.ingest(self.envelope(p,Fernet.generate_key()))
    def test_expired_token(self):
        p=report();token=Fernet(self.app.config['key'].encode()).encrypt_at_time(json.dumps(dict(report=p,nonce=secrets.token_hex(24))).encode(),int(time.time()-400))
        with self.assertRaises(ValueError):self.app.ingest(token)
    def test_offline_no_alarm(self):
        p=report(drive({197:2}));p['collected_at']-=1000
        self.app.store.save(p)
        self.app.alarms()
        self.assertTrue(self.app.state()['nodes'][0]['stale'])
        self.assertEqual(self.app.store.events(),[])
    def test_persistence_and_out_of_order(self):
        p=report();self.app.store.save(p)
        p['collected_at']-=10
        self.assertFalse(self.app.store.save(p))
        fresh=Store(Path(self.tmp.name))
        self.assertEqual(len(fresh.nodes()),1)
        self.assertEqual(len(fresh.history('test',p['drives'][0]['id'])),1)
    def test_deduplicated_alarms(self):
        self.app.store.save(report(drive({197:2})))
        self.app.alarms();self.app.alarms()
        self.assertEqual(len(self.app.store.events()),1)
    def test_settings_validate_before_write(self):
        old=self.app.config['interval']
        with self.assertRaises(ValueError):self.app.settings({'interval':1})
        self.assertEqual(self.app.config['interval'],old)
    def test_http_auth_remote_isolation_and_delivery(self):
        self.app.start_server('127.0.0.1',19765)
        self.app.start_server('127.0.0.1',19766,True)
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen('http://127.0.0.1:19765/api/state')
        self.assertEqual(e.exception.code,401)
        e.exception.close()
        req=urllib.request.Request('http://127.0.0.1:19765/api/state',headers={'Authorization':'Bearer '+self.app.ui_token})
        with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['role'],'hub')
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen('http://127.0.0.1:19766/api/state')
        self.assertEqual(e.exception.code,404)
        e.exception.close()
        req=urllib.request.Request('http://127.0.0.1:19766/api/v1/report',data=self.envelope(report()))
        with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
    def test_malformed_report(self):
        p=report();p['drives'][0]['metrics']['x']=float('nan')
        with self.assertRaises(ValueError):validate_report(p)
    def test_missing_drive(self):
        p=report();self.app.store.save(p);p=copy.deepcopy(p);p['collected_at']+=1;p['drives']=[];self.app.store.save(p)
        self.assertEqual(len(self.app.state()['nodes'][0]['missing']),1)

if __name__=='__main__':unittest.main()
