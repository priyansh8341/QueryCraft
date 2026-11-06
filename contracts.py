"""Conservative, explicit semantic checks. These cover defined cases, not arbitrary English."""
import re
import sqlglot
from sqlglot import exp
from engine import QueryError

def capability_gap(question,tables):
    q=question.lower();cols={c['name'].lower() for t in tables for c in t['columns']}
    if re.search(r'\brevenue\b',q) and not any(any(token in c for token in ('revenue','price','sales_amount','sale_amount','transaction_amount')) for c in cols):
        return 'Revenue is not defined in the selected data: no revenue, sales-amount or price fields are available. Select a suitable business dataset or define the required measure.'
    if re.search(r'\b(profit|profitability|margin)\b',q) and not any('cost' in c or 'profit' in c for c in cols):
        return 'Profit requires cost data. These tables contain revenue and refunds, but no costs. Upload cost data or ask for net revenue after refunds.'
    if re.search(r'\b(roas|advertising spend|ad spend|return on advertising)\b',q) and not any('spend' in c or 'advertis' in c for c in cols):
        return 'Advertising spend is not available. Upload a spend dataset and specify its relationship to orders before calculating advertising returns.'
    if re.search(r'\b(best|worst)\b',q) and not re.search(r'\b(revenue|refund|orders|spend|quantity|value|growth)\b',q):
        return 'Which measure should define best or worst: completed revenue, order count, refund rate or another metric?'
    if re.search(r'\b(shipping|delivery)\b',q) and re.search(r'\b(duration|time|days|speed)\b',q) and not any('deliver' in c or 'ship' in c for c in cols):
        return 'Delivery duration cannot be calculated: this dataset has no shipment or delivery timestamps. Upload those records and define their relationship to orders.'
    ranges=[v for t in tables for v in t.get('date_ranges',{}).values() if v[1]]
    if re.search(r'\b(revenue|orders?|sales)\b',q):
        business_dates=[t['date_ranges']['order_date'] for t in tables if t.get('name') in ('orders','completed_sales') and t.get('date_ranges',{}).get('order_date')]
        if business_dates:ranges=business_dates
    years=[int(y) for y in re.findall(r'\b(20\d{2})\b',q)]
    maxyear=max((int(v[1][:4]) for v in ranges),default=9999)
    if years and max(years)>maxyear:
        return f'The available date columns end in {maxyear}. There are no observed records for {max(years)}. Upload that period or explicitly request a separately evaluated forecasting workflow.'
    return None

def check_dimensions(question,result):
    # Small declared contract: direct named dimensions must appear in output.
    q=question.lower();aliases={'channel':['channel'],'country':['country'],'category':['category'],'product':['product_name','product_id'],'customer':['customer_id']}
    cols=' '.join(result['columns']).lower()
    patterns={
      'channel':r'\b(?:by|per|each)\s+channels?\b',
      'country':r'\b(?:by|per|each)\s+(?:customer\s+)?countr(?:y|ies)\b',
      'category':r'\b(?:by|per|each)\s+(?:product\s+)?categor(?:y|ies)\b',
      'product':r'\b(?:by|per|each)\s+products?\b(?!\s+categor)',
      'customer':r'\b(?:by|per|each)\s+customers?\b(?!\s+countr)',
    }
    for dim,allowed in aliases.items():
        if re.search(patterns[dim],q) and not any(a in cols for a in allowed):
            raise QueryError(f'The question requests grouping by {dim}, but the output omits that dimension. Include an explicitly named {allowed[0]} output column and group at that grain.')

def check_temporal_grain(question,sql):
    """Reject a known quarter-vs-single-month error; not a universal date-proof system."""
    if not re.search(r'\bq[1-4]\b|\bquarters?\b',question.lower()):return
    if re.search(r'\b(first|last|single)\s+month\b',question.lower()):return
    tree=sqlglot.parse_one(sql,read='duckdb')
    for eq in tree.find_all(exp.EQ):
        for extractor,other in [(eq.this,eq.expression),(eq.expression,eq.this)]:
            if isinstance(extractor,(exp.Month,exp.Extract)) and isinstance(other,exp.Literal) and not other.is_string:
                unit='MONTH' if isinstance(extractor,exp.Month) else str(extractor.this).upper()
                if unit=='MONTH':raise QueryError('A whole-quarter question cannot be answered by selecting a single month. Use EXTRACT(QUARTER FROM order_date) with quarter numbers 1-4, or full three-month date ranges. Preserve the requested output columns.')

def check_projection_contract(question,sql):
    """Keep requested grouping labels and explicit rounding precision in LLM output."""
    tree=sqlglot.parse_one(sql,read='duckdb');issues=[]
    if isinstance(tree,exp.Select):
        group=tree.args.get('group')
        selected=[]
        for projection in tree.expressions:
            value=projection.this if isinstance(projection,exp.Alias) else projection
            if not value.find(exp.AggFunc):selected.append(value)
        names={c.name.lower() for v in selected for c in v.find_all(exp.Column)}
        for value in group.expressions if group else []:
            if isinstance(value,exp.Column) and value.name.lower() not in names and value.name.lower() not in {p.alias.lower() for p in tree.expressions if p.alias}:
                issues.append(f'Include grouping label {value.name} in the SELECT output, not only GROUP BY.')
    if re.search(r'\b(two|2) decimal',question.lower()):
        for rounding in tree.find_all(exp.Round):
            places=rounding.args.get('decimals')
            if not isinstance(places,exp.Literal) or places.this!='2':issues.append('The question requests two decimals. Use ROUND(expression, 2), not ROUND(expression).')
    if issues:raise QueryError(' '.join(issues))
