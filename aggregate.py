"""Small typed compiler for single-table CSV aggregation; not unrestricted text-to-SQL."""
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict
from sqlglot import exp
from engine import QueryError

class AggregatePlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation:Literal['count','count_distinct','avg','sum','min','max']
    column:str
    group_by:str
    filter_column:str
    filter_operator:Literal['eq','ne','gt','gte','lt','lte']
    filter_value:str

def operation_for(question):
    q=question.lower()
    if re.search(r'\b(average|mean)\b',q):return 'avg'
    if re.search(r'\b(maximum|max|highest)\b',q):return 'max'
    if re.search(r'\b(minimum|min|lowest)\b',q):return 'min'
    if re.search(r'\b(how many|count|number of)\b',q):return 'count_distinct' if 'distinct' in q else 'count'
    if re.search(r'\b(sum|total)\b',q):return 'sum'
    return None

def schema_for(table,question):
    names=[c['name'] for c in table['columns']];schema=AggregatePlan.model_json_schema()
    op=operation_for(question);schema['properties']['operation']['enum']=[op]
    for prop in ['column','group_by','filter_column']:schema['properties'][prop]['enum']=names+(['*'] if prop=='column' else ['none'])
    q=question.lower();explicit=[]
    for name in names:
        if re.search(r'\bby\s+(?:the\s+)?'+re.escape(name.replace('_',' '))+r'\b',q) or re.search(r'\bby\s+'+re.escape(name)+r'\b',q):explicit.append(name)
    schema['properties']['group_by']['enum']=explicit if len(explicit)==1 else ['none']
    quoted=re.findall(r"'([^']*)'",question)
    if len(quoted)==1:
        schema['properties']['filter_value']['enum']=quoted
        prefix=question.split("'",1)[0].lower()
        match=re.search(r'([a-z][a-z0-9_]*)\s+(?:is|=|equals?|equal\s+to)\s*$',prefix)
        if match and match[1] in names:schema['properties']['filter_column']['enum']=[match[1]]
    elif not re.search(r'\b(where|after|before|greater|less|above|below|equal|in\s+20\d{2})\b',q):
        schema['properties']['filter_column']['enum']=['none']
    return schema

def compile_aggregate(table,plan,question):
    columns={c['name']:c['type'] for c in table['columns']}
    if plan.operation!=operation_for(question):raise QueryError('The aggregation must match the measure explicitly requested by the question.')
    if plan.column not in columns and not(plan.column=='*' and plan.operation=='count'):raise QueryError('Invalid aggregate column.')
    if plan.group_by!='none' and plan.group_by not in columns:raise QueryError('Invalid grouping column.')
    if plan.filter_column!='none' and plan.filter_column not in columns:raise QueryError('Invalid filter column.')
    if plan.operation in ('avg','sum') and not any(t in columns[plan.column] for t in ['INT','DECIMAL','DOUBLE','FLOAT','REAL','HUGEINT']):raise QueryError('Averages and sums require a numeric column.')
    schema=schema_for(table,question)
    if plan.group_by not in schema['properties']['group_by']['enum']:raise QueryError('Grouping does not match the explicit request.')
    quoted=re.findall(r"'([^']*)'",question)
    if len(quoted)==1 and (plan.filter_column=='none' or plan.filter_value!=quoted[0]):raise QueryError('Use the exact explicitly quoted filter value and a real filter column.')
    identifier=lambda name:exp.to_identifier(name,quoted=True).sql(dialect='duckdb')
    col='*' if plan.column=='*' else identifier(plan.column)
    aggregation=f'COUNT(DISTINCT {col})' if plan.operation=='count_distinct' else f'{plan.operation.upper()}({col})'
    if plan.operation in ('avg','sum','min','max') and any(t in columns[plan.column] for t in ['INT','DECIMAL','DOUBLE','FLOAT','REAL']):aggregation=f'ROUND({aggregation},2)'
    group='' if plan.group_by=='none' else identifier(plan.group_by)
    where=''
    if plan.filter_column!='none':
        operator={'eq':'=','ne':'!=','gt':'>','gte':'>=','lt':'<','lte':'<='}[plan.filter_operator]
        where=f'WHERE {identifier(plan.filter_column)} {operator} {exp.Literal.string(plan.filter_value).sql(dialect="duckdb")}'
    return f'SELECT {(group+", ") if group else ""}{aggregation} AS {plan.operation}_value FROM {identifier(table["name"])} {where} '+(f'GROUP BY {group} ORDER BY {group}' if group else '')
