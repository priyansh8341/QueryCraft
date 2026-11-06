import sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import duckdb,pytest
from seed import create_demo
from engine import execute,schema,QueryError
from comparison import QuarterPlan,period_request,validate_intent,compile_quarters

@pytest.fixture(scope='module',params=[83041,73129])
def data(request,tmp_path_factory):
    path=tmp_path_factory.mktemp('comparison')/'data.duckdb';create_demo(path,request.param);return path

def independent_totals(path):
    # Python row accumulation over raw tables; no SQL aggregation or semantic view.
    with duckdb.connect(str(path),read_only=True) as con:
        rows=con.execute("SELECT o.order_date, p.product_name, i.quantity, i.unit_price, i.discount_pct, r.refund_id FROM orders o JOIN order_items i USING(order_id) JOIN products p USING(product_id) LEFT JOIN refunds r USING(order_item_id) WHERE o.status='completed'").fetchall()
    totals={};products={}
    for date,name,qty,price,discount,refund in rows:
        quarter=(date.month-1)//3+1
        if quarter not in (3,4):continue
        value=qty*price*(1-discount)
        totals[quarter]=totals.get(quarter,Decimal(0))+value
        item=products.setdefault((name,quarter),[Decimal(0),0,0]);item[0]+=value;item[1]+=1;item[2]+=refund is not None
    return totals,products

def test_full_quarters_match_independent_row_math(data):
    q='Compare completed revenue in Q3 and Q4 2025, including percentage growth.'
    period=period_request(q,schema(data));plan=QuarterPlan(metric='revenue',dimension='total',include_refund_rate=False)
    validate_intent(q,plan);actual=execute(data,compile_quarters(plan,period,q))['rows'][0]
    expected,_=independent_totals(data)
    assert abs(actual[0]-float(expected[3]))<.01
    assert abs(actual[1]-float(expected[4]))<.01
    assert abs(actual[2]-round(float(100*(expected[4]-expected[3])/expected[3]),2))<.01

def test_product_growth_and_refunds_match_independent_math(data):
    q='Which products grew revenue from Q3 to Q4 2025 while their refund rate increased?'
    plan=QuarterPlan(metric='revenue',dimension='product',include_refund_rate=True)
    validate_intent(q,plan)
    actual=execute(data,compile_quarters(plan,period_request(q,schema(data)),q))['rows']
    _,products=independent_totals(data);expected=[]
    for name in {k[0] for k in products}:
        a=products.get((name,3));b=products.get((name,4))
        if a and b and b[0]>a[0] and b[2]/b[1]>a[2]/a[1]:expected.append(name)
    assert sorted(row[0] for row in actual)==sorted(expected)
    for row in actual:
        a=products[(row[0],3)];b=products[(row[0],4)]
        assert abs(row[1]-float(a[0]))<.01 and abs(row[2]-float(b[0]))<.01

def test_plan_cannot_silently_change_measure_or_group():
    with pytest.raises(QueryError):validate_intent('Compare net revenue Q3 and Q4',QuarterPlan(metric='revenue',dimension='total',include_refund_rate=False))
    with pytest.raises(QueryError):validate_intent('Compare revenue by product Q3 and Q4',QuarterPlan(metric='revenue',dimension='total',include_refund_rate=False))
    with pytest.raises(QueryError):compile_quarters(QuarterPlan(metric='revenue',dimension='total',include_refund_rate=False),{'year':2025,'previous':0,'current':99},'')

def test_zero_baseline_returns_null(data):
    period={'year':2023,'previous':3,'current':4}
    result=execute(data,compile_quarters(QuarterPlan(metric='revenue',dimension='total',include_refund_rate=False),period,''))
    assert result['rows']==[[None,None,None]]
