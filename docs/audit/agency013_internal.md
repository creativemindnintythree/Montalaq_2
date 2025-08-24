\# Agency 013 — Internal Audit Notes (v0.13.4)



\## Persistence \& Idempotency Rules

\- `TradeAnalysis` rows are \*\*idempotent\*\*:

&nbsp; - Enforced by \*\*DB-level uniqueness\*\* on `(symbol, timeframe, bar\_ts)`.

&nbsp; - Any duplicate writes are rejected (`ErrorCode.DUPLICATE\_WRITE`).

\- Writes use `get\_or\_create()` inside a transaction.

\- Regression contract:

&nbsp; - Same tick replay = \*\*0 duplicate rows\*\*.



---



\## NO\_TRADE Contract

\- If rules return `final\_decision == "NO\_TRADE"`:

&nbsp; - ✅ An `AnalysisLog` entry is written (`COMPLETE`).

&nbsp; - ❌ No `TradeAnalysis` row is persisted.

\- Regression contract:

&nbsp; - 10× NO\_TRADE cycles = \*\*0 rows in TradeAnalysis\*\*.



---



\## Freshness Gating Behavior

\- Scheduler enqueues `analyze\_latest` \*\*only if freshness == GREEN\*\*.

\- If freshness is \*\*AMBER or RED\*\*:

&nbsp; - Analysis is skipped.

&nbsp; - `AnalysisLog` entry is written with reason `STALE\_DATA`.

\- Ensures \*\*no analysis on stale bars\*\*.



---



\## Quiet vs Broken Feed Semantics

\- `IngestionStatus.last\_seen\_at` updated every cycle.

\- Heartbeat exposed in `/api/ingestion/status`:

&nbsp; - `Healthy` → Fresh data within expected interval.

&nbsp; - `Connected – no new ticks` → Provider connected but no new bars (quiet market).

&nbsp; - `Provider stale` → Missed beats or feed outage.



---



\## Regression / Soak Test Notes

\- \*\*Idempotency\*\*:

&nbsp; - Run repeated ticks → verify no duplicate rows.

\- \*\*NO\_TRADE\*\*:

&nbsp; - Run 10× NO\_TRADE → verify no persistence.

\- \*\*Freshness\*\*:

&nbsp; - GREEN → analysis runs.

&nbsp; - AMBER/RED → analysis skipped, log written.

\- \*\*Heartbeat\*\*:

&nbsp; - Simulate market closed → API shows “Connected – no new ticks”.

&nbsp; - Simulate feed outage → API shows “Provider stale”.

\- \*\*Soak\*\*:

&nbsp; - Run weekend/holiday (no trades) to confirm quiet vs broken is distinguished.



---



\## References

\- `backend/models.py` → Idempotency \& heartbeat fields.

\- `backend/tasks/analysis\_tasks.py` → NO\_TRADE persistence discipline.

\- `backend/tasks/scheduler.py` → Freshness gating.

\- `backend/tasks/freshness.py` → Updates `last\_seen\_at` + freshness state.

\- `backend/api/status/serializers.py` → Heartbeat logic.

\- `backend/errors.py` → Error taxonomy (`E0134\_\*`).

\- Tests:

&nbsp; - `tests/test\_agent0134\_idempotency.py`

&nbsp; - `tests/test\_agent0134\_no\_trade.py`

&nbsp; - `tests/test\_agent0134\_freshness.py`

&nbsp; - `tests/test\_agent0134\_heartbeat.py`



