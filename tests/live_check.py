"""Read-only hardware check, encrypted loopback delivery; no external destination."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Application
from collector import collect
root=Path(__file__).resolve().parents[1]/'build/live-check'
hub=Application('hub',root/'hub',ui_port=19965,api_port=19966)
agent=Application('agent',root/'agent',ui_port=19967)
try:
    hub.start_server('127.0.0.1',19966,True)
    agent.settings({'hub_url':'http://127.0.0.1:19966','key':hub.config['key']})
    report=collect()
    report.update(node_id=agent.config['node_id'],node_name=agent.config['node_name'],interval=300)
    agent.store.save(report)
    agent.deliver(report)
    nodes=hub.state()['nodes']
    assert len(nodes)==1,'Bericht fehlt auf Zentrale'
    assert len(nodes[0]['drives'])==len(report['drives'])
    result={'delivery':agent.delivery,'devices':len(report['drives']),'readable':sum(d['readable'] for d in report['drives']),
            'drives':[{'protocol':d['protocol'],'metric_count':len(d['metrics']),'readable':d['readable'],'partial':d['partial']} for d in report['drives']]}
    (root/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
finally:
    agent.quit();hub.quit()
    for s in hub.servers:s.server_close()
