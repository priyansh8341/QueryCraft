import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import duckdb,pytest
from aggregate import AggregatePlan,compile_aggregate,schema_for
from engine import execute,QueryError
TABLE={'name':'observations','columns':[{'name':'kind','type':'VARCHAR'},{'name':'value','type':'DOUBLE'}]}

def test_typed_aggregate_missing_values_and_literal_escaping(tmp_path):
    path=tmp_path/'test.duckdb'
    with duckdb.connect(str(path)) as con:
        con.execute('CREATE TABLE observations(kind VARCHAR,value DOUBLE)')
        con.executemany('INSERT INTO observations VALUES (?,?)',[('rain',2),('rain',4),('rain',None),("x'; DROP TABLE observations; --",9)])
    plan=AggregatePlan(operation='avg',column='value',group_by='kind',filter_column='none',filter_operator='eq',filter_value='')
    r=execute(path,compile_aggregate(TABLE,plan,'Average value by kind'))
    assert ['rain',3.0] in r['rows']
    injection="x'; DROP TABLE observations; --"
    plan=AggregatePlan(operation='count',column='*',group_by='none',filter_column='kind',filter_operator='eq',filter_value=injection)
    sql=compile_aggregate(TABLE,plan,'How many records where kind equals the supplied value?')
    assert execute(path,sql)['rows']==[[1]]
    assert execute(path,'SELECT count(*) FROM observations')['rows']==[[4]]

def test_dynamic_schema_and_rejected_columns():
    schema=schema_for(TABLE,"How many records where kind is 'rain'?")
    assert schema['properties']['filter_column']['enum']==['kind']
    assert schema['properties']['filter_value']['enum']==['rain']
    with pytest.raises(QueryError):compile_aggregate(TABLE,AggregatePlan(operation='avg',column='kind',group_by='none',filter_column='none',filter_operator='eq',filter_value=''),'Average kind')
    with pytest.raises(QueryError):compile_aggregate(TABLE,AggregatePlan(operation='avg',column='secret',group_by='none',filter_column='none',filter_operator='eq',filter_value=''),'Average secret')
