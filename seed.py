"""Deterministic, synthetic commerce data. Not real customer or trading data."""
import random
from datetime import date, timedelta
import duckdb

SEED = 83041
METRICS = '''Dataset: synthetic commerce, 2025-01-01 through 2025-12-31. Currency: AED.
Orders: one row per order. Items: one row per order/product combination.
Completed revenue = SUM(quantity * unit_price * (1 - discount_pct)) for orders.status = 'completed'.
Gross revenue excludes refunds; net revenue subtracts refunds.amount from completed revenue.
Refunds: zero or one row per order_item_id. Refund rate means refunded completed items / completed items, not refunded units.
Order count counts DISTINCT order_id. Average order value = completed revenue / distinct completed orders.
Never sum order-level quantities after joining line items without handling duplication.
Use stored item.unit_price for revenue, not product.list_price.
Customer country is the billing country. Order channel is web, app or partner.
Quarter comparisons use calendar quarters in 2025. Latest quarter is 2025 Q4; previous is Q3.
For growth: (current - previous) / previous; report undefined when previous is zero.
No profit, advertising spend, exchange rates, support tickets or future data are provided.
Preferred semantic view: completed_sales (one row per completed order_item).
completed_sales has revenue_aed (already discounted), refund_aed (zero if none),
net_revenue_aed, refunded_item (0 or 1), order_id, order_item_id, customer_id,
order_date, channel, country, segment, product_id, product_name, category, quantity.
For revenue use SUM(revenue_aed). For net revenue use SUM(net_revenue_aed).
For AOV use SUM(revenue_aed)/COUNT(DISTINCT order_id). Refund rate = AVG(refunded_item)*100.
The view excludes cancelled/pending orders. Query raw orders for all-status questions.
'''

VIEW_SQL='''CREATE OR REPLACE VIEW completed_sales AS
SELECT i.order_item_id, o.order_id, o.customer_id, o.order_date, o.channel,
 c.country, c.segment, p.product_id, p.product_name, p.category,
 i.quantity, i.unit_price, i.discount_pct,
 i.quantity*i.unit_price*(1-i.discount_pct) AS revenue_aed,
 COALESCE(r.amount,0) AS refund_aed,
 i.quantity*i.unit_price*(1-i.discount_pct)-COALESCE(r.amount,0) AS net_revenue_aed,
 CASE WHEN r.refund_id IS NOT NULL THEN 1 ELSE 0 END AS refunded_item
FROM order_items i JOIN orders o USING(order_id)
JOIN customers c USING(customer_id) JOIN products p USING(product_id)
LEFT JOIN refunds r USING(order_item_id)
WHERE o.status='completed'
'''

def ensure_view(path):
    with duckdb.connect(str(path)) as con:con.execute(VIEW_SQL)

def create_demo(path,seed=SEED):
    rng=random.Random(seed)
    con=duckdb.connect(str(path))
    con.execute('CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, country VARCHAR, segment VARCHAR, joined_date DATE)')
    con.execute('CREATE TABLE products(product_id INTEGER PRIMARY KEY, product_name VARCHAR, category VARCHAR, list_price DECIMAL(12,2))')
    con.execute('CREATE TABLE orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date DATE, status VARCHAR, channel VARCHAR)')
    con.execute('CREATE TABLE order_items(order_item_id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price DECIMAL(12,2), discount_pct DECIMAL(5,2))')
    con.execute('CREATE TABLE refunds(refund_id INTEGER PRIMARY KEY, order_item_id INTEGER, refund_date DATE, amount DECIMAL(12,2), reason VARCHAR)')
    customers=[(i,rng.choice(['UAE','Saudi Arabia','Oman','Qatar']),rng.choice(['consumer','business']),date(2024,1,1)+timedelta(days=rng.randrange(365))) for i in range(1,241)]
    products=[(1,'Atlas Headphones','Electronics',349),(2,'Nova Keyboard','Electronics',229),(3,'Orbit Monitor','Electronics',899),(4,'Terra Backpack','Accessories',179),(5,'Flow Bottle','Accessories',79),(6,'Arc Desk Lamp','Home',149),(7,'Cloud Chair','Home',649),(8,'Pulse Watch','Electronics',499),(9,'Trail Shoes','Lifestyle',299),(10,'Linen Set','Home',249),(11,'Aero Mouse','Electronics',119),(12,'Metro Wallet','Accessories',99)]
    orders=[];items=[];refunds=[]
    for oid in range(1,1801):
        day=date(2025,1,1)+timedelta(days=rng.randrange(365))
        status=rng.choices(['completed','cancelled','pending'],[.87,.08,.05])[0]
        orders.append((oid,rng.randrange(1,241),day,status,rng.choice(['web','app','partner'])))
        # Deliberate, discoverable Q4 volume/refund shift for Atlas; not an answer hardcoded in queries.
        pool=list(range(1,13))+([1,1,8] if day.month>=10 else [])
        pids=rng.sample(list(range(1,13)),rng.randrange(1,5))
        if day.month>=10 and rng.random()<.45 and 1 not in pids:pids[0]=1
        for pid in pids:
            iid=len(items)+1; qty=rng.randrange(1,4);price=products[pid-1][3];discount=rng.choice([0,0,.05,.10,.15])
            items.append((iid,oid,pid,qty,price,discount))
            rate=.26 if pid==1 and day.month>=10 else .065
            if status=='completed' and rng.random()<rate:
                refunds.append((len(refunds)+1,iid,day+timedelta(days=rng.randrange(1,15)),round(qty*price*(1-discount),2),rng.choice(['damaged','changed_mind','wrong_item'])))
    con.execute('BEGIN')
    for table,rows in [('customers',customers),('products',products),('orders',orders),('order_items',items),('refunds',refunds)]:
        con.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in rows[0])})',rows)
    con.execute('COMMIT');con.execute(VIEW_SQL);con.execute('CHECKPOINT');con.close()

RELATIONS=[('orders.customer_id','customers.customer_id'),('order_items.order_id','orders.order_id'),('order_items.product_id','products.product_id'),('refunds.order_item_id','order_items.order_item_id')]
