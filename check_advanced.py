"""Live advanced cases plus an independent row-calculation oracle."""
import json,time
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
import duckdb
from seed import METRICS
from engine import schema
from llm import generate
ROOT=Path(__file__).parent;path=ROOT/'data/demo.duckdb'
with duckdb.connect(str(path),read_only=True) as con:
    rows=con.execute("SELECT o.order_date,p.product_name,i.quantity,i.unit_price,i.discount_pct,r.refund_id FROM orders o JOIN order_items i USING(order_id) JOIN products p USING(product_id) LEFT JOIN refunds r USING(order_item_id) WHERE o.status='completed'").fetchall()
totals=defaultdict(lambda:[Decimal(0),0,0])
for date,name,qty,price,discount,refund in rows:
    q=(date.month-1)//3+1
    cell=totals[(name,q)];cell[0]+=qty*price*(1-discount);cell[1]+=1;cell[2]+=refund is not None
expected=[]
for name in {k[0] for k in totals}:
    a=totals[(name,3)];b=totals[(name,4)]
    if a[1] and b[1] and b[0]>a[0] and b[2]/b[1]>a[2]/a[1]:expected.append(name)
questions=['Compare completed revenue in Q3 and Q4 2025. Return Q3 revenue, Q4 revenue and percentage growth rounded to two decimals.','Which products grew revenue from Q3 to Q4 2025 while their refund rate increased?']
results=[]
for question in questions:
    start=time.perf_counter();r=generate(question,schema(path),METRICS,path)
    actual=r.get('result',{}).get('rows',[])
    correct=actual==[[582290.4,546644.75,-6.12]] if len(results)==0 else r['status']=='complete' and sorted(row[0] for row in actual)==sorted(expected)
    results.append({'question':question,'correct':correct,'seconds':round(time.perf_counter()-start,2),'payload':r})
    print(question,r['status'],correct,flush=True)
(ROOT/'evidence/advanced-live.json').write_text(json.dumps({'method':'Independent Python accumulation over raw line-item rows for product selection; full-quarter total checked against raw-table reference. Developer-authored cases informed implementation.','cases':results},indent=2))
