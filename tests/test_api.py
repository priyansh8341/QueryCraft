import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['QUERYCRAFT_DATA']=tempfile.mkdtemp(prefix='querycraft-test-')
from fastapi.testclient import TestClient
import server

def test_isolated_history_export_and_workspace():
    a=TestClient(server.app);b=TestClient(server.app)
    wa=a.get('/api/workspace').json();assert len(wa['tables'])==6
    r=a.post('/api/query',json={'sql':'SELECT count(*) AS n FROM orders'})
    assert r.status_code==200;run=r.json();assert run['result']['rows']==[[1800]]
    assert len(a.get('/api/history').json())==1
    assert b.get('/api/history').json()==[]
    assert b.get('/api/export/'+run['id']).status_code==404
    assert '1800' in a.get('/api/export/'+run['id']).text

def test_csv_import_inference_validation_and_isolation():
    a=TestClient(server.app);b=TestClient(server.app)
    r=a.post('/api/upload',data={'table_name':'campaigns'},files={'file':('campaigns.csv',b'channel,spend\nweb,120.5\napp,230.0\n','text/csv')})
    assert r.status_code==200
    assert a.post('/api/query',json={'sql':'SELECT sum(spend) FROM campaigns'}).json()['result']['rows']==[[350.5]]
    assert b.post('/api/query',json={'sql':'SELECT * FROM campaigns'}).status_code==400
    assert a.post('/api/upload',data={'table_name':'orders'},files={'file':('x.csv',b'x\n1\n')}).status_code==409
    assert a.post('/api/upload',data={'table_name':'../x'},files={'file':('x.csv',b'x\n1\n')}).status_code==400
    assert a.post('/api/upload',data={'table_name':'bad'},files={'file':('x.csv',b'x,x\n1,2\n')}).status_code==400
    assert a.post('/api/upload',data={'table_name':'bad'},files={'file':('x.csv',b'x,y\n1\n')}).status_code==400

def test_origin_host_and_destructive_queries():
    a=TestClient(server.app)
    assert a.post('/api/query',json={'sql':'SELECT 1'},headers={'origin':'https://evil.test'}).status_code==403
    assert a.get('/api/workspace',headers={'host':'evil.test'}).status_code==400
    assert a.post('/api/query',json={'sql':'DROP TABLE orders'}).status_code==400
    assert a.post('/api/query',json={'sql':'SELECT count(*) FROM orders'}).json()['result']['rows']==[[1800]]

def test_ai_failure_is_recorded_without_fabricated_result(monkeypatch):
    monkeypatch.setattr(server,'generate',lambda *args:{'status':'failed','message':'Model unavailable','trace':[]})
    a=TestClient(server.app);r=a.post('/api/ask',json={'question':'What is completed revenue?'})
    assert r.status_code==200;assert r.json()['status']=='failed';assert 'result' not in r.json()
    assert not list((server.DATA/a.cookies['qc_workspace']).glob('*.duckdb'))==[]
    assert len(list((server.DATA/a.cookies['qc_workspace']).glob('*.duckdb')))==1

def test_export_formula_protection():
    a=TestClient(server.app);r=a.post('/api/query',json={'sql':"SELECT '=1+1' AS untrusted_value"}).json()
    assert "'=1+1" in a.get('/api/export/'+r['id']).text
    r=a.post('/api/query',json={'sql':'SELECT \'  =1+1\' AS "=formula"'}).json()
    output=a.get('/api/export/'+r['id']).text
    assert "'=formula" in output and "'  =1+1" in output

def test_source_scope_enforced_for_editor_and_prompt(monkeypatch):
    a=TestClient(server.app)
    assert a.post('/api/query',json={'sql':'SELECT * FROM orders','sources':['products']}).status_code==400
    assert a.post('/api/query',json={'sql':'SELECT * FROM orders','sources':['missing']}).status_code==400
    a.post('/api/upload',data={'table_name':'weather'},files={'file':('w.csv',b'date,temperature\n2020-01-01,24\n')})
    captured={}
    def fake(question,tables,metrics,path):
        captured.update(tables=tables,metrics=metrics)
        return {'status':'clarify','message':'test','trace':[]}
    monkeypatch.setattr(server,'generate',fake)
    r=a.post('/api/ask',json={'question':'What is average temperature?','sources':['weather']})
    assert r.status_code==200 and [t['name'] for t in captured['tables']]==['weather']
    assert 'Preferred semantic view' not in captured['metrics']

def test_export_trace_and_access_control(monkeypatch):
    a=TestClient(server.app);b=TestClient(server.app)
    run=a.post('/api/query',json={'sql':'SELECT 42 AS n'}).json()
    assert a.get('/api/export/'+run['id']+'/json').json()['analysis']['result']['rows']==[[42]]
    assert b.get('/api/export/'+run['id']+'/json').status_code==404
    monkeypatch.setenv('QUERYCRAFT_ACCESS_PASSWORD','test-password-not-a-real-secret')
    assert a.get('/api/workspace').status_code==401
    assert a.get('/api/workspace',auth=('demo','wrong')).status_code==401
    assert a.get('/api/workspace',auth=('demo','test-password-not-a-real-secret')).status_code==200
    assert a.get('/api/live').status_code==200
