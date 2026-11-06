"""Supplementary regression questions. Their first run was post-development;
shipping clarification review informed a subsequent fix. They are NOT held-out.
"""
CASES=[
 {'id':'h_cancelled','category':'filter','question':'How many orders were cancelled in 2025?','sql':"SELECT count(*) cancelled_orders FROM orders WHERE status='cancelled'"},
 {'id':'h_customers','category':'distinct grain','question':'How many distinct customers placed a completed order in 2025?','sql':"SELECT count(DISTINCT customer_id) customers FROM orders WHERE status='completed'"},
 {'id':'h_net_channel','category':'net revenue grouping','question':'Show net revenue after refunds by channel in AED.','sql':"SELECT o.channel,round(sum(i.quantity*i.unit_price*(1-i.discount_pct)-coalesce(r.amount,0)),2) net_revenue_aed FROM orders o JOIN order_items i USING(order_id) LEFT JOIN refunds r USING(order_item_id) WHERE o.status='completed' GROUP BY 1 ORDER BY 1"},
 {'id':'h_refund_reason','category':'grouping','question':'Show the total refunded amount by refund reason.','sql':"SELECT reason,round(sum(amount),2) refunded_aed FROM refunds GROUP BY 1 ORDER BY 1"},
 {'id':'h_units','category':'units','question':'How many units were sold in completed orders in total?','sql':"SELECT sum(i.quantity) units FROM orders o JOIN order_items i USING(order_id) WHERE o.status='completed'"},
 {'id':'h_shipping','category':'unavailable data','question':'What is the average shipping delivery duration in days?','clarify':True},
]
