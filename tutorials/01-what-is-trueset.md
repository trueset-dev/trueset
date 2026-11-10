# Video 01 — What is trueset & why

**Length:** ~80s · **Goal:** the hook — checks pass, data's still wrong between
systems. **Record in your own voice.** Talk to one person; the lines below are a
safety net, not a straitjacket.

| # | On screen | Narration (say it naturally) |
|---|-----------|------------------------------|
| 1 | Title card: trueset logo + "open-source data quality & reconciliation" | "This is trueset — an open-source data-quality tool. Let me show you the problem it solves." |
| 2 | Big line: "Your pipeline passed every test. The numbers are still wrong." | "If you work with data, you've shipped a pipeline that passed every check — and still delivered wrong numbers. No job failed, no alert fired. But the total in the warehouse didn't match the source." |
| 3 | "dbt tests · Great Expectations · Soda — one table at a time" | "Most tools check one table at a time. They're good — but they can't see the problems that live *between* systems. A value that quietly changed on the way in. A row that vanished in a pipeline hop." |
| 4 | The reconcile result panel: row_count_parity ✓, referential_integrity ✗·1, value_parity ✗·3 — "Row counts matched. The values didn't." | "trueset catches exactly that. It compares two systems row by row — so silent corruption can't hide behind matching totals." |
| 5 | "Write once · run anywhere — pandas · DuckDB · your warehouse" | "And you write a check once. It runs unchanged on pandas, on DuckDB, or pushed straight into your warehouse." |
| 6 | Terminal: `$ pip install trueset` | "It's open source, Apache-2.0, and it's one pip install. Free, on PyPI today." |
| 7 | Title card: "Next → your first check" | "In the next video I'll show you your first check — from nothing to a passing validation in two minutes. Let's go." |

**Post caption idea (LinkedIn):** "Your pipeline passed every test and the numbers
are still wrong. That's the gap I built trueset to close — open-source, one
`pip install`. 🧵 First look 👇"
