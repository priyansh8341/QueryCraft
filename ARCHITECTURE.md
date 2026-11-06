# Architecture and engineering decisions

```text
React / TypeScript
  → FastAPI API + workspace cookie
    → explicit source scope (enforced for AI and SQL editor)
    → schema and metric context
    → capability checks (missing cost/spend, ambiguous ranking, date coverage)
    → choose one declared route:
        quarter comparison → constrained intent → server SQL compiler
        single-CSV aggregate → schema-constrained intent → server SQL compiler
        other questions → structured free-form SQL → one bounded repair
    → narrowly scoped date literal normalization
    → SQLGlot AST policy
    → restricted read-only DuckDB + watchdog + result cap
    → explicit dimension checks
    → result + SQL + trace → SQLite history → chart/table/CSV

Failed SQL → one model repair → same validation/execution path
Missing data → clarification, no fabricated answer
```

## Why a semantic view?

The initial model joined at the wrong grain and generated invalid nested aggregates. `completed_sales` centralizes discounted revenue and refund calculations at the completed-item grain. It is a database view, not a separate copied dataset. AOV still needs DISTINCT order IDs; the view does not magically solve all grain mistakes. Independent reference SQL uses base tables so a shared view expression cannot trivially validate itself.

## Typed semantic compilers

`comparison.py` owns full-quarter boundaries, grouped period aggregation, percentage growth, refund-rate denominators and missing/zero-baseline behavior. The question parser establishes explicit calendar periods and grouping constraints. The model selects the typed measure/filter intent within those constraints; the server compiles SQL. Narrative comparison insights are templates over executed result cells, not model-generated causal claims.

`aggregate.py` handles one operation over one selected CSV: count, distinct count, average, sum, min or max, optional explicit grouping and one filter. JSON-schema enums come from the selected schema and explicit grouping/literal constraints. SQL identifiers and filter literals are escaped with SQLGlot. The model cannot invent a column or replace ROUND(x,2) with whole-number rounding on this route. This deliberately bounded route is not a universal query language.

Both compiler routes still run through the AST policy, restricted DuckDB connection and output cap. Free-form questions use the original SQL route and can still be semantically wrong.

## Why DuckDB, not the history database?

DuckDB performs analytical joins/aggregations and CSV type inference. SQLite stores application history. Keeping these responsibilities separate also prevents an analytical SELECT from reading application sessions/history.

## Why a bounded workflow instead of an autonomous agent?

The task is a question with a bounded database result. One generation and one repair keep execution understandable and cap model calls. The model cannot invoke arbitrary tools. The trace distinguishes generated SQL, normalization and execution from correctness.

## Source isolation and transport

CSV scope removes commerce definitions from model context and restricts executable table names, not merely the UI dropdown. Application history is stored in a different database. Optional cloud inference uses a server-only OpenAI Responses adapter with strict JSON schemas, store=false and refusal/incomplete-output checks. Its request handling is mocked in tests; real cloud inference was not exercised. Local Ollama is the verified release provider.

## Concurrency and persistence

CSV imports and direct SQL use a process lock. AI requests copy the workspace database under that lock, then analyze the immutable snapshot. A two-slot semaphore limits concurrent analyses. The local service uses one Uvicorn process; multi-worker deployment needs stronger cross-process coordination. Workspaces and history persist under ignored `data/`; model snapshots are deleted after each request.

## Important limitations

- A missing grouping dimension can be detected for declared phrases; arbitrary English semantics cannot.
- The small local model can produce valid but incorrect SQL, especially period comparisons. A declared quarter-vs-single-month check now rejects the observed month-equality mistake; this does not prove arbitrary temporal semantics correct. Quarter guidance is added only to quarter questions after a global prompt experiment caused unrelated queries to gain a Q4 filter.
- Metric definitions currently target the seeded commerce schema. Uploaded tables need human relationship/metric review.
- Date typing normalization is deterministic and narrow. It does not invent answers or change arithmetic.
- Query time/memory settings are defense in depth, not a substitute for container/process isolation.
- The UI shows model-proposed reasoning as an approach, not verified evidence. Clarification after a failed repair is treated as generation failure rather than disguising a model SQL problem as missing user information.
- Charts show up to 50 returned rows; CSV contains up to the 500-row result cap. Neither is a full dataset export.

## Next production gates

Multi-user identity beyond the implemented Basic demo gate; per-user quotas; isolated worker processes; durable job execution; cleanup policies; larger blinded evaluation; monitoring; a formal accessibility audit; and verified hosted deployment. These are production extensions, not unfinished local application flows.
