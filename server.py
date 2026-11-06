from pathlib import Path
import base64, csv, io, json, os, re, secrets, shutil, sqlite3, threading, time, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import duckdb, httpx
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from seed import create_demo, ensure_view, METRICS, RELATIONS
from engine import schema, execute, QueryError
from llm import generate, MODEL, OLLAMA
from model_client import PROVIDER,LOCAL

ROOT=Path(__file__).parent
DATA=Path(os.getenv('QUERYCRAFT_DATA',ROOT/'data'));DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock();slots=threading.BoundedSemaphore(2)
def metadata():
    con=sqlite3.connect(DATA/'history.sqlite');con.row_factory=sqlite3.Row
    return con
with metadata() as con:
    con.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,workspace TEXT,created TEXT,question TEXT,mode TEXT,payload TEXT)')
if not (DATA/'demo.duckdb').exists():create_demo(DATA/'demo.duckdb')
ensure_view(DATA/'demo.duckdb')
for old in DATA.glob('*/workspace.duckdb'):ensure_view(old)

app=FastAPI(title='QueryCraft',docs_url='/api/docs',redoc_url=None)
@app.middleware('http')
async def boundaries(request,call_next):
    # Local prototype: authenticated deployment is a separate gate.
    host=request.headers.get('host','').split(':')[0]
    if host not in os.getenv('QUERYCRAFT_ALLOWED_HOSTS','127.0.0.1,localhost,testserver').split(','):return JSONResponse({'detail':'Unknown host'},400)
    origin=request.headers.get('origin')
    if origin and origin not in os.getenv('QUERYCRAFT_ALLOWED_ORIGINS','http://127.0.0.1:8040,http://localhost:8040,http://testserver').split(','):return JSONResponse({'detail':'Origin not allowed'},403)
    if request.url.path=='/api/live':return JSONResponse({'status':'ok'})
    password=os.getenv('QUERYCRAFT_ACCESS_PASSWORD')
    if host not in ('127.0.0.1','localhost','testserver') and not password:
        return JSONResponse({'detail':'Public access requires server-side access authentication.'},503)
    if password:
        try:
            kind,encoded=request.headers.get('authorization','').split(' ',1)
            user,provided=base64.b64decode(encoded,validate=True).decode().split(':',1)
            valid=kind.lower()=='basic' and secrets.compare_digest(user,os.getenv('QUERYCRAFT_ACCESS_USER','demo')) and secrets.compare_digest(provided,password)
        except (ValueError,UnicodeError):valid=False
        if not valid:return JSONResponse({'detail':'Authentication required'},401,headers={'WWW-Authenticate':'Basic realm="QueryCraft", charset="UTF-8"'})
    if request.headers.get('content-length','0').isdigit() and int(request.headers.get('content-length','0'))>6_000_000:return JSONResponse({'detail':'Request exceeds 6 MB'},413)
    sid=request.cookies.get('qc_workspace','')
    fresh=not re.fullmatch('[0-9a-f]{32}',sid)
    if fresh:sid=secrets.token_hex(16)
    request.state.workspace=sid
    with LOCK:
        folder=DATA/sid
        if not folder.exists():
            if sum(1 for p in DATA.iterdir() if p.is_dir() and re.fullmatch('[0-9a-f]{32}',p.name))>=int(os.getenv('QUERYCRAFT_MAX_WORKSPACES','250')):
                return JSONResponse({'detail':'Workspace capacity reached. Reuse an existing session or contact the owner.'},429)
            folder.mkdir();shutil.copy2(DATA/'demo.duckdb',folder/'workspace.duckdb')
    response=await call_next(request)
    if fresh:response.set_cookie('qc_workspace',sid,httponly=True,samesite='strict',secure=os.getenv('QUERYCRAFT_SECURE_COOKIE')=='1',max_age=604800)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return response

def db(req):return DATA/req.state.workspace/'workspace.duckdb'
def record(req,question,mode,payload):
    ident=uuid.uuid4().hex
    with metadata() as con:con.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(ident,req.state.workspace,datetime.now(timezone.utc).isoformat(),question,mode,json.dumps(payload)))
    return dict(payload,id=ident)

@app.get('/api/workspace')
def workspace(request:Request):
    with LOCK:tables=schema(db(request))
    return {'name':'Commerce sandbox','source':'Deterministic synthetic dataset · seed 83041','tables':tables,'relationships':RELATIONS,'metrics':METRICS,'model':MODEL,'limits':{'rows':500,'seconds':5,'memory':'256 MB'}}

@app.get('/api/health')
def health():
    if PROVIDER=='openai':
        configured=bool(os.getenv('OPENAI_API_KEY') and MODEL)
        return {'status':'ok','model':MODEL or 'Not configured','model_available':configured,'provider':PROVIDER,'local':False,'model_status':'configured_not_verified' if configured else 'missing_configuration'}
    try:
        with httpx.Client(timeout=2,trust_env=False) as client:
            models=client.get(OLLAMA+'/api/tags').json().get('models',[])
        available=any(x.get('name')==MODEL for x in models)
    except Exception:available=False
    return {'status':'ok','model':MODEL,'model_available':available,'provider':PROVIDER,'local':LOCAL,'model_status':'connected' if available else 'offline'}

class SQLRequest(BaseModel):
    sql:str=Field(min_length=1,max_length=16000)
    sources:list[str]|None=Field(default=None,max_length=10)
class AskRequest(BaseModel):
    question:str=Field(min_length=5,max_length=1500)
    sources:list[str]|None=Field(default=None,max_length=10)

def scope_tables(tables,sources):
    if sources is None:return tables
    names={t['name'] for t in tables}
    if not sources or any(s not in names for s in sources):raise HTTPException(400,'Choose one or more existing data sources.')
    return [t for t in tables if t['name'] in sources]

@app.post('/api/query')
def query(body:SQLRequest,request:Request):
    if not slots.acquire(blocking=False):raise HTTPException(429,'Two queries are already running. Try again shortly.')
    try:
        with LOCK:
            tables=scope_tables(schema(db(request)),body.sources)
            result=execute(db(request),body.sql,allowed_tables=[t['name'] for t in tables])
        return record(request,'SQL: '+body.sql.strip().replace('\n',' ')[:100],'sql',{'status':'complete','result':result,'sources':[t['name'] for t in tables],'trace':[{'stage':'validation_and_execution','status':'passed','ms':result['elapsed_ms']}]})
    except QueryError as e:raise HTTPException(400,str(e))
    finally:slots.release()

@app.post('/api/ask')
def ask(body:AskRequest,request:Request):
    if not slots.acquire(blocking=False):raise HTTPException(429,'Two analyses are already running. Try again shortly.')
    snapshot=DATA/request.state.workspace/(uuid.uuid4().hex+'.duckdb')
    try:
        with LOCK:
            shutil.copy2(db(request),snapshot)
            tables=scope_tables(schema(snapshot),body.sources)
        has_commerce=any(t['name']=='completed_sales' for t in tables)
        metrics=METRICS if has_commerce else 'User-selected tables. No commerce metric definitions or verified relationships apply. Use only these selected tables and their actual column names. Ask for clarification when a requested business measure or relationship is not defined. NULL values are missing, not zero. Do not invent a currency or measurement unit.'
        payload=generate(body.question,tables,metrics,snapshot)
        payload['sources']=[t['name'] for t in tables]
        return record(request,body.question,'ai',payload)
    finally:
        snapshot.unlink(missing_ok=True)
        slots.release()

@app.get('/api/history')
def history(request:Request):
    with metadata() as con:rows=con.execute('SELECT * FROM runs WHERE workspace=? ORDER BY created DESC LIMIT 30',(request.state.workspace,)).fetchall()
    return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]

@app.get('/api/export/{ident}')
def export(ident:str,request:Request):
    with metadata() as con:row=con.execute('SELECT payload FROM runs WHERE id=? AND workspace=?',(ident,request.state.workspace)).fetchone()
    if not row:raise HTTPException(404,'Result not found')
    result=json.loads(row[0]).get('result')
    if not result:raise HTTPException(400,'This analysis has no result to export')
    protect=lambda v:"'"+v if isinstance(v,str) and (v.lstrip()[:1] in ('=','+','-','@') or v[:1] in ('\t','\r','\n')) else v
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow([protect(v) for v in result['columns']])
    # CSV exports opened in spreadsheets must not interpret untrusted strings as formulae.
    writer.writerows([[protect(v) for v in row] for row in result['rows']])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="querycraft-result.csv"'})

@app.get('/api/export/{ident}/json')
def export_trace(ident:str,request:Request):
    with metadata() as con:row=con.execute('SELECT created,question,mode,payload FROM runs WHERE id=? AND workspace=?',(ident,request.state.workspace)).fetchone()
    if not row:raise HTTPException(404,'Analysis not found')
    return JSONResponse({'export_version':1,'id':ident,'created':row['created'],'question':row['question'],'mode':row['mode'],'analysis':json.loads(row['payload'])},headers={'Content-Disposition':'attachment; filename="querycraft-analysis.json"'})

@app.post('/api/upload')
async def upload(request:Request,file:UploadFile=File(...),table_name:str=Form(...)):
    if not re.fullmatch('[a-z][a-z0-9_]{0,39}',table_name):raise HTTPException(400,'Use a lowercase table name with letters, numbers and underscores.')
    raw=await file.read(5_000_001)
    if len(raw)>5_000_000:raise HTTPException(413,'CSV maximum size is 5 MB.')
    try:
        text=raw.decode('utf-8-sig');reader=csv.reader(io.StringIO(text));headers=next(reader)
        if not 1<=len(headers)<=30 or len(set(h.lower() for h in headers))!=len(headers):raise ValueError('Provide 1–30 unique columns.')
        if any(not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,49}',h) for h in headers):raise ValueError('Column names must start with a letter and contain only letters, numbers or underscores.')
        count=0
        for row in reader:
            count+=1
            if len(row)!=len(headers):raise ValueError(f'Row {count+1} has the wrong number of columns.')
            if count>50000:raise ValueError('Maximum 50,000 rows per upload.')
        if not count:raise ValueError('CSV has no data rows.')
    except (ValueError,UnicodeError,StopIteration,csv.Error) as e:raise HTTPException(400,str(e) or 'Invalid CSV')
    path=DATA/request.state.workspace/(uuid.uuid4().hex+'.csv')
    with LOCK:
        existing=schema(db(request))
        if table_name in [x['name'] for x in existing]:raise HTTPException(409,'That table already exists. Choose a new name.')
        if len(existing)>=10:raise HTTPException(400,'Workspace limit is 10 tables.')
        path.write_bytes(raw)
        try:
            with duckdb.connect(str(db(request))) as con:
                con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM read_csv(?, header=true, auto_detect=true)',[str(path)])
        except duckdb.Error as e:raise HTTPException(400,str(e)[:300])
        finally:path.unlink(missing_ok=True)
    return {'table':table_name,'rows':count,'note':'Types inferred from CSV. Inspect schema before analysis; relationships for uploaded tables are not automatically verified.'}

@app.get('/api/evaluation')
def evaluation():
    path=ROOT/'evidence/evaluation.json'
    report=json.loads(path.read_text()) if path.exists() else {'status':'not_run','cases':[]}
    extra=ROOT/'evidence/holdout.json'
    if extra.exists():report['additional']=json.loads(extra.read_text())
    external=ROOT/'evidence/external-data.json'
    if external.exists():report['external']=json.loads(external.read_text())
    return report

DIST=ROOT/'web/dist'
if DIST.exists():app.mount('/',StaticFiles(directory=DIST,html=True),name='web')
