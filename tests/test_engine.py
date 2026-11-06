import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from seed import create_demo
from engine import execute,validate_sql,QueryError,schema
from benchmark import CASES

@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    path=tmp_path_factory.mktemp('db')/'demo.duckdb';create_demo(path);return path

def test_all_reference_queries_execute(demo):
    for c in CASES:
        if 'sql' in c:
            r=execute(demo,c['sql']);assert not r['truncated'];assert r['columns']

@pytest.mark.parametrize('sql',[
 'DROP TABLE orders','SELECT 1; SELECT 2',"SELECT * FROM read_csv('secret.csv')",
 "SELECT * FROM read_parquet('https://evil.test/a')",'SELECT * FROM information_schema.tables',
 'SELECT * FROM sqlite_scan(\'x\',\'y\')','SELECT * FROM nonexistent','SELECT getenv(\'HOME\')',
 'COPY orders TO \'x.csv\'','SELECT * INTO foo FROM orders','ATTACH \'x\' AS y',
 'SELECT query(\'DROP TABLE orders\')','SELECT * FROM range(100000000000)',
 'WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT * FROM x) SELECT * FROM x',
 'SELECT * FROM duckdb_settings()','SELECT * FROM main.orders',
])
def test_reject_unsafe(sql):
    with pytest.raises(QueryError):validate_sql(sql,['orders'])

def test_output_cap(demo):
    r=execute(demo,'SELECT * FROM orders');assert len(r['rows'])==500;assert r['truncated']

def test_join_grain_and_refunds(demo):
    total=execute(demo,CASES[0]['sql'])['rows'][0][0]
    refund=execute(demo,CASES[7]['sql'])['rows'][0][0]
    net=execute(demo,CASES[8]['sql'])['rows'][0][0]
    assert abs(total-refund-net)<.01

def test_schema_counts(demo):
    s={t['name']:t for t in schema(demo)}
    assert s['orders']['rows']==1800;assert s['customers']['rows']==240;assert s['products']['rows']==12
    assert all(not t['nulls'] for t in s.values())

def test_semantic_view_matches_independent_reference(demo):
    view=execute(demo,'SELECT round(sum(revenue_aed),2),round(sum(net_revenue_aed),2),round(100.0*avg(refunded_item),2) FROM completed_sales')['rows'][0]
    for n,case in enumerate([CASES[0],CASES[8],CASES[9]]):assert abs(view[n]-execute(demo,case['sql'])['rows'][0][0])<.01
