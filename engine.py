"""SQL AST policy plus independently restricted DuckDB connections.

AST checks are not a general SQL sandbox. A narrow function allowlist,
disabled external access, process memory setting and a query watchdog form
additional controls. Production hostile multi-tenant execution requires OS isolation.
"""
import datetime, decimal, threading, time
from pathlib import Path
import duckdb
import sqlglot
from sqlglot import exp

class QueryError(ValueError):pass

FUNCTIONS=set('sum count avg min max round abs coalesce nullif cast try_cast date_trunc extract year month quarter day strftime lower upper length trim concat concat_ws substring replace regexp_replace greatest least if case when date_diff date_add date_sub timestampdiff current_date row_number rank dense_rank lag lead first_value last_value ntile cume_dist percent_rank power sqrt floor ceil ceiling stddev_pop stddev_samp variance var_pop var_samp median quantile_cont quantile_disc count_if bool_and bool_or string_agg array_agg arg_max arg_min any_value filter array_size array_length'.split())
FUNCTIONS.update({'timestamp_trunc','ts_or_ds_to_timestamp','ts_or_ds_to_date','time_to_str','date_to_di','strpos','safe_divide','and','or','not'})

def validate_sql(sql, tables):
    if len(sql)>16000:raise QueryError('SQL is too long (16,000 characters maximum).')
    try:parsed=sqlglot.parse(sql,read='duckdb')
    except sqlglot.errors.ParseError as e:raise QueryError(f'SQL could not be parsed: {str(e)[:220]}')
    if len(parsed)!=1 or not isinstance(parsed[0],(exp.Select,exp.Union,exp.Intersect,exp.Except)):
        raise QueryError('Only one read-only SELECT query is allowed.')
    tree=parsed[0]
    blocked=('Insert','Update','Delete','Create','Drop','Alter','Command','Copy','Attach','Detach','Pragma','Set','Use','Into','Transaction','Merge','Grant','Revoke','Execute','LoadData')
    for name in blocked:
        cls=getattr(exp,name,None)
        if cls and tree.find(cls):raise QueryError(f'{name} is not allowed.')
    if any(w.args.get('recursive') for w in tree.find_all(exp.With)):raise QueryError('Recursive queries are disabled.')
    ctes={c.alias.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog or not isinstance(table.this,exp.Identifier):
            raise QueryError('External sources and qualified database names are disabled.')
        if table.name.lower() not in set(tables)|ctes:raise QueryError(f'Table {table.name!r} is not in this workspace.')
    for fn in tree.find_all(exp.Func):
        name=(fn.name if isinstance(fn,exp.Anonymous) else fn.sql_name()).lower()
        if name not in FUNCTIONS:raise QueryError(f'Function {name!r} is outside the allowed analytics functions.')
    return tree.sql(dialect='duckdb')

def normalize_date_literals(sql):
    """Only type bare ISO-date literals used as date_trunc inputs. Never change filters or arithmetic."""
    try:tree=sqlglot.parse_one(sql,read='duckdb')
    except sqlglot.errors.ParseError as e:raise QueryError(str(e)[:250])
    if tree is None:raise QueryError('The model returned empty SQL.')
    changed=False
    for node in tree.find_all(exp.TimestampTrunc):
        arg=node.this
        if isinstance(arg,exp.Literal) and arg.is_string and __import__('re').fullmatch(r'\d{4}-\d{2}-\d{2}',arg.this):
            node.set('this',exp.Cast(this=arg.copy(),to=exp.DataType.build('DATE')));changed=True
    return (tree.sql(dialect='duckdb') if changed else sql),changed

def serialize(v):
    if isinstance(v,decimal.Decimal):return float(v)
    if isinstance(v,(datetime.datetime,datetime.date,datetime.time)):return v.isoformat()
    if isinstance(v,float) and not __import__('math').isfinite(v):return None
    if isinstance(v,(list,dict,bytes)):return str(v)[:2000]
    return v

def connect(path):
    return duckdb.connect(str(path),read_only=True,config={'enable_external_access':'false','threads':'2','memory_limit':'256MB','max_expression_depth':'100'})

def schema(path):
    with connect(path) as con:
        result=[]
        for table,kind in con.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name").fetchall():
            cols=con.execute(f'DESCRIBE "{table}"').fetchall()
            count=con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            sample=con.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
            quality=[]
            date_ranges={}
            for c in cols:
                col=c[0].replace('"','""')
                nulls=con.execute(f'SELECT count(*) FROM "{table}" WHERE "{col}" IS NULL').fetchone()[0]
                if nulls:quality.append({'column':c[0],'nulls':nulls})
                if 'DATE' in c[1] or 'TIMESTAMP' in c[1]:
                    lo,hi=con.execute(f'SELECT min("{col}"),max("{col}") FROM "{table}"').fetchone()
                    date_ranges[c[0]]=[serialize(lo),serialize(hi)]
            result.append({'name':table,'kind':'view' if kind=='VIEW' else 'table','rows':count,'columns':[{'name':c[0],'type':c[1]} for c in cols], 'sample':[[serialize(v) for v in r] for r in sample], 'nulls':quality,'date_ranges':date_ranges})
        return result

def execute(path,sql,max_rows=500,timeout=5,allowed_tables=None):
    names=[x['name'] for x in schema(path)]
    if allowed_tables is not None:names=[n for n in names if n in allowed_tables]
    normalized=validate_sql(sql,names)
    start=time.perf_counter(); con=connect(path)
    timer=threading.Timer(timeout,con.interrupt);timer.daemon=True
    try:
        timer.start()
        # An outer cap bounds materialized output even if the model omits LIMIT.
        cur=con.execute(f'SELECT * FROM ({normalized}) AS _querycraft_result LIMIT {max_rows+1}')
        columns=[x[0] for x in cur.description]; rows=cur.fetchall()
        return {'sql':normalized,'columns':columns,'rows':[[serialize(v) for v in row] for row in rows[:max_rows]],'truncated':len(rows)>max_rows,'row_limit':max_rows,'elapsed_ms':round((time.perf_counter()-start)*1000,1)}
    except duckdb.Error as e:raise QueryError(str(e)[:600])
    finally:
        timer.cancel();timer.join();con.close()
