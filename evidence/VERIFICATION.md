# Completed local release verification â€” 6 November 2026

- Python checks: 47 passed (one Starlette/httpx TestClient deprecation warning).
- Frontend: TypeScript check and Vite production build passed.
- Development regression: 18/18 expected outcomes matched; median 4.54 seconds including deterministic clarifications.
- Supplementary regression: 6/6 expected outcomes matched; median 4.33 seconds.
- Public weather-data regression: 8/8 expected outcomes matched, using a separate Python csv/statistics oracle.
- Advanced live comparison checks: 2/2 correct. Product selection checked using Python accumulation over raw line-item rows.
- All sets informed fixes. Questions are developer-authored; none is blinded, independently reviewed or held-out. Clarification scoring checks status only.
- Quarter comparison now completes through a typed intent and server SQL compiler. Result math is also checked independently on two different synthetic seeds.
- Authored quarter SQL example executes and returns Q3 AED 582,290.40, Q4 AED 546,644.75 and growth -6.12%.
- The shipping capability check now explicitly identifies absent shipment/delivery timestamps.
- Browser: quarter KPI result; public CSV import; isolated CSV aggregation; correct weather result table; numerical sorting; JSON download; history restoration; chart rendering; and evaluation report inspected. Final screenshots are in this directory.
- Not verified: Docker image build, hosted deployment, independent evaluation, arbitrary-data analytical correctness.

Source fingerprints are retained alongside raw experiment evidence. No production-user or general accuracy claim is supported by this local release.

GitHub Actions passed Python checks and the frontend production build on Linux: https://github.com/priyansh8341/QueryCraft/actions/runs/42218865535
