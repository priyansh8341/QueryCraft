import argparse,datetime,json,statistics,time,math
from pathlib import Path
from benchmark import CASES
from seed import METRICS,create_demo,ensure_view
from engine import execute,schema
from llm import generate,MODEL

def canonical(rows):
    # Column aliases and order do not determine correctness; values and row multiplicity do.
    def cell(v):
        if isinstance(v,(int,float)):return ('number',round(float(v),2))
        if v is None:return ('null','')
        return ('text',str(v).replace('T00:00:00',''))
    return sorted([tuple(cell(v) for v in r) for r in rows],key=repr)

def compare(actual,expected):
    if len(actual)!=len(expected):return False
    a=canonical(actual);e=canonical(expected)
    # Match numeric cells with rounding tolerance, preserve each row and column's position.
    for row1,row2 in zip(a,e):
        if len(row1)!=len(row2):return False
        for (t,v),(t2,v2) in zip(row1,row2):
            if t!=t2:return False
            if t=='number':
                if not math.isclose(v,v2,abs_tol=.02,rel_tol=.000001):return False
            elif v!=v2:return False
    return True

def run(limit=None,holdout=False):
    root=Path(__file__).parent;path=root/'data/benchmark.duckdb';path.parent.mkdir(exist_ok=True)
    if not path.exists():create_demo(path)
    ensure_view(path)
    tables=schema(path);rows=[]
    if holdout:
        from holdout import CASES as selected_cases
    else:selected_cases=CASES
    for case in selected_cases[:limit]:
        start=time.perf_counter();payload=generate(case['question'],tables,METRICS,path)
        actual=payload.get('result',{}).get('rows',[])
        reference=execute(path,case['sql']) if 'sql' in case else None
        expected=reference['rows'] if reference else None
        correct=payload['status']=='clarify' if case.get('clarify') else payload['status']=='complete' and not payload['result']['truncated'] and len(payload['result']['columns'])==len(reference['columns']) and compare(actual,expected)
        rows.append({'id':case['id'],'question':case['question'],'category':case['category'],'correct':bool(correct),'status':payload['status'] if correct else ('wrong_result' if payload['status']=='complete' else payload['status']),'seconds':round(time.perf_counter()-start,2),'reference':expected,'actual':actual,'payload':payload})
        print(case['id'],rows[-1]['status'],correct,flush=True)
        report={'status':'complete' if len(rows)==len(selected_cases[:limit]) else 'in_progress','split':'supplementary regression' if holdout else 'development','created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model':MODEL,'total':len(rows),'correct':sum(r['correct'] for r in rows),'executed':sum(r['payload']['status']=='complete' for r in rows),'median_seconds':round(statistics.median(r['seconds'] for r in rows),2),'method':'Developer-authored synthetic regression benchmark. Reference result values compared within 0.02 AED; column positions and counts matter, row order ignored. Clarification cases scored by status only; wording requires human review. Both sets have informed implementation fixes. Neither independent nor held-out.','cases':rows}
        (root/'evidence').mkdir(exist_ok=True);(root/('evidence/holdout.json' if holdout else 'evidence/evaluation.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);parser.add_argument('--holdout',action='store_true');args=parser.parse_args();run(args.limit,args.holdout)
