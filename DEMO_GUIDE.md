# Five-minute demonstration

1. Open http://127.0.0.1:8040. State clearly: synthetic commerce dataset, local portfolio application.
2. Open Data sources. Show the orders-to-items relationship and the completed_sales view. Explain why line-item joins can overcount orders.
3. Ask: **What is completed revenue by month in 2025?** Show the chart, then Results and SQL. Explain discounted revenue and completed-only filtering.
4. Open Trace. Show that successful execution is not a correctness guarantee. A small model generated the query; the server enforced execution restrictions.
5. Ask: **What is our profit margin by product?** Demonstrate missing-cost clarification instead of inventing profit from revenue minus refunds.
6. In SQL editor, try `SELECT * FROM read_csv('private.csv')`. Show rejection. Explain external access is independently disabled in DuckDB.
7. Open Query history and restore the monthly analysis. Export its CSV.
8. Open Evaluation. Describe the current measured results including incorrect cases. Do not present developer-authored cases as an independent benchmark.

## Demonstrate the temporal fix

Ask the Q3/Q4 comparison question from the benchmark. The earlier model selected July and October only. The current typed route extracts intent and compiles complete calendar quarters in server code. Show Q3 AED 582,290.40, Q4 AED 546,644.75 and -6.12% growth. Open Trace and explain the difference between model-extracted intent and compiled SQL. The authored `examples/quarter_revenue.sql` independently demonstrates the same calculation in the editor; do not label that authored example as model-generated.

Ask **Which products grew revenue from Q3 to Q4 2025 while their refund rate increased?** Show the product measures and explain the item-count refund denominator.

## Show another schema

Import fixtures/weather.csv as weather. The Analyse selector switches to that source. Ask **Show average wind by weather type, rounded to two decimals.** Expected values: drizzle 2.37, fog 2.48, rain 3.67, snow 4.41, sun 2.96. Sort Results by avg_value, then export Analysis JSON. Explain that source scope is enforced in the server, not just suggested to the model.

## If the local model is offline

The UI reports it. Switch to SQL editor and run the built-in monthly example. Explain that this demonstrates the data/execution path, not an AI result. Never label SQL examples as live LLM output.

## Good interview story

“The first version produced invalid revenue SQL. A semantic view fixed the join grain, but the model still confused months and quarters. I moved declared comparison math into a typed compiler, constrained the model's intent to the request and checked results with independent row calculations. I also found a missing grouping label and invented revenue in a weather dataset, which led to typed CSV aggregation and source-aware capability checks. Free-form SQL remains less constrained, so I expose its query and trace.”

Use this story only after reproducing the workflow and understanding the code. Credit substantial AI assistance honestly and explain your reviewed contributions.
