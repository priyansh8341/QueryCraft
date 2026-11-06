"""Typed, compiled quarter analytics. The model chooses intent; Python owns SQL arithmetic.

Only this declared semantic schema is supported. It is not a general SQL compiler.
"""
import re
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
from engine import QueryError

Metric=Literal['revenue','net_revenue','orders','units','refund_rate','aov']
Dimension=Literal['total','product','category','country','channel']
class QuarterPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    metric:Metric=Field(description='Primary requested measure; revenue means gross completed revenue, net_revenue subtracts refunds')
    dimension:Dimension=Field(description='Grouping requested by the question, or total')
    include_refund_rate:bool=Field(description='True only when refund rate is requested as a second measure')

def period_request(question,tables):
    q=question.lower()
    quarters=sorted(set(int(x) for x in re.findall(r'\bq([1-4])\b',q)))
    comparative=bool(re.search(r'\b(compare|comparison|versus|vs|growth|grew|increased|change|higher)\b',q))
    if not comparative:return None
    date_ranges=[t.get('date_ranges',{}).get('order_date') for t in tables if t['name']=='completed_sales']
    last=next((r[1] for r in date_ranges if r and r[1]),None)
    years=set(int(x) for x in re.findall(r'\b(20\d{2})\b',q))
    if len(quarters)==2:
        if len(years)>1:raise QueryError('This comparison supports two quarters in one calendar year. Specify a single year.')
        year=next(iter(years)) if years else int(last[:4]) if last else None
    elif last and re.search(r'\b(last|latest) quarter\b',q):
        year=int(last[:4]);current=(int(last[5:7])-1)//3+1
        if current==1:raise QueryError('Cross-year quarter comparison is not supported by this comparison plan. Specify two quarters in one year.')
        quarters=[current-1,current]
    else:return None
    if year is None:raise QueryError('Specify the calendar year for this quarter comparison.')
    return {'year':year,'previous':quarters[0],'current':quarters[1]}

def declared_intent(question):
    q=question.lower()
    expected='total'
    if re.search(r'\bproducts?\b',q) and not re.search(r'\bproduct categor',q):expected='product'
    elif re.search(r'\bcategor(?:y|ies)\b',q):expected='category'
    elif re.search(r'\bcountr(?:y|ies)\b',q):expected='country'
    elif re.search(r'\bchannels?\b',q):expected='channel'
    if 'net revenue' in q:metric='net_revenue'
    elif 'average order' in q or re.search(r'\baov\b',q):metric='aov'
    elif 'revenue' in q:metric='revenue'
    elif re.search(r'\bunits?\b',q):metric='units'
    elif 'refund rate' in q:metric='refund_rate'
    elif re.search(r'\borders?\b',q):metric='orders'
    else:raise QueryError('Specify the measure to compare: revenue, net revenue, orders, units, refund rate or average order value.')
    refunds='refund rate' in q and metric!='refund_rate'
    return QuarterPlan(metric=metric,dimension=expected,include_refund_rate=refunds)

def validate_intent(question,plan):
    expected=declared_intent(question)
    if plan.dimension!=expected.dimension:raise QueryError(f'The requested grouping is {expected.dimension}; the plan proposed {plan.dimension}.')
    if plan.metric!=expected.metric:raise QueryError(f'The requested primary measure is {expected.metric}; the plan proposed {plan.metric}.')
    if plan.include_refund_rate!=expected.include_refund_rate:raise QueryError('The plan must include refund rate only when explicitly requested.')

def compile_quarters(plan,period,question):
    """Only validated enum expressions and bounded integers enter SQL. No user text is SQL."""
    year=int(period['year']);a=int(period['previous']);b=int(period['current'])
    if not 1900<=year<=2100 or not 1<=a<b<=4:raise QueryError('Invalid calendar comparison periods.')
    dim={'total':None,'product':'product_name','category':'category','country':'country','channel':'channel'}[plan.dimension]
    expressions={'revenue':'SUM(revenue_aed)','net_revenue':'SUM(net_revenue_aed)','orders':'COUNT(DISTINCT order_id)','units':'SUM(quantity)','refund_rate':'100.0*AVG(refunded_item)','aov':'SUM(revenue_aed)/NULLIF(COUNT(DISTINCT order_id),0)'}
    measure=expressions[plan.metric]
    by=(dim+', ') if dim else ''
    group=('GROUP BY '+dim+', period') if dim else 'GROUP BY period'
    pivot_group='GROUP BY '+dim if dim else ''
    fields=f"{by}MAX(CASE WHEN period={a} THEN measure END) AS previous_value, MAX(CASE WHEN period={b} THEN measure END) AS current_value"
    if plan.include_refund_rate:fields+=f", MAX(CASE WHEN period={a} THEN refund_rate END) AS previous_refund_rate, MAX(CASE WHEN period={b} THEN refund_rate END) AS current_refund_rate"
    primary=plan.metric+'_aed' if plan.metric in ('revenue','net_revenue','aov') else plan.metric
    projection=f'{by}ROUND(previous_value,2) AS q{a}_{primary}, ROUND(current_value,2) AS q{b}_{primary}, ROUND(100.0*(current_value-previous_value)/NULLIF(previous_value,0),2) AS growth_pct'
    if plan.include_refund_rate:projection+=f', ROUND(previous_refund_rate,2) AS q{a}_refund_rate_pct, ROUND(current_refund_rate,2) AS q{b}_refund_rate_pct, ROUND(current_refund_rate-previous_refund_rate,2) AS refund_change_pp'
    conditions=[];q=question.lower()
    if dim and re.search(r'\b(grew|increased|higher|growth)\b',q) and plan.metric in ('revenue','net_revenue'):conditions.append('current_value > previous_value')
    if plan.include_refund_rate and re.search(r'\b(increased|higher|more)\b.*refund|refund.*\b(increased|higher|more)\b',q):conditions.append('current_refund_rate > previous_refund_rate')
    where='WHERE '+ ' AND '.join(conditions) if conditions else ''
    order='ORDER BY growth_pct DESC NULLS LAST, '+dim if dim else ''
    return f'''WITH quarterly AS (
      SELECT {by}EXTRACT(QUARTER FROM order_date) AS period, {measure} AS measure,
             100.0*AVG(refunded_item) AS refund_rate
      FROM completed_sales
      WHERE EXTRACT(YEAR FROM order_date)={year}
        AND EXTRACT(QUARTER FROM order_date) IN ({a},{b})
      {group}
    ), compared AS (SELECT {fields} FROM quarterly {pivot_group})
    SELECT {projection} FROM compared {where} {order}'''

def result_summary(plan,period,result):
    """Describe only executed result cells; no generated narrative or causal claim."""
    if plan.dimension!='total' or len(result['rows'])!=1:return f"Returned {len(result['rows'])} {plan.dimension} groups for the requested quarter comparison. Inspect each measure in Results."
    previous,current,growth=result['rows'][0][:3]
    label=plan.metric.replace('_',' ')
    if previous is None or current is None:return f'{label.capitalize()} is missing for one or both requested quarters. Growth is undefined.'
    if growth is None:return f'The earlier-quarter {label} baseline is zero. Percentage growth is undefined.'
    direction='increased' if growth>0 else 'decreased' if growth<0 else 'did not change'
    change=f' by {abs(growth):,.2f}%' if growth else ''
    return f"{label.capitalize()} {direction}{change} from Q{period['previous']} to Q{period['current']} {period['year']} ({previous:,.2f} → {current:,.2f})."
