# MET-A: In-Memory Session Query Audit Backend

## Executive Summary

QueryTrace has no audit trail for live `/query` calls — the only observability is static benchmarks via `/evals`. This batch adds an in-memory session audit that logs every successful `/query` call as q013+, exposed via a new `GET /session-audit` endpoint. No disk persistence, no SQLite, no frontend changes.

## Task Blocks

---

### T1 — Initialize thread-safe audit store (P0)

**What to do:** Add module-level state to `src/main.py` alongside existing `_evals_cache`:
- `_session_audit: List[dict] = []`
- `_session_audit_lock = threading.Lock()`
- `_session_started_at: str` — set to `datetime.now(timezone.utc).isoformat()` at module load time
- `_BENCHMARK_COUNT: int` — derived from `len(load_test_queries(_EVALS_PATH))` at module load time

**Why:** All subsequent tasks depend on this store existing. The lock is required because FastAPI sync endpoints run on a threadpool, making concurrent `/query` calls possible.

**Acceptance criteria:**
- `_session_audit` is an empty list at process start
- `_session_started_at` is a valid UTC ISO-8601 string
- `_BENCHMARK_COUNT == 12` (current benchmark file)
- `threading.Lock` is used, not `asyncio.Lock`

**Files affected:** `src/main.py`

---

### T2 — Extract audit entry from PipelineResult and append after successful /query (P1)

**What to do:** After the existing `QueryResponse` construction in `def query()` (main.py ~line 129), add a try/except block that:
1. Acquires `_session_audit_lock`
2. Computes `live_index = len(_session_audit) + 1`
3. Computes `qid = f"q{_BENCHMARK_COUNT + live_index:03d}"`
4. Builds an audit entry dict from `result.trace` (DecisionTrace) with this shape:
   ```
   {
     "id": qid,
     "created_at": <utc iso-8601>,
     "query": request.query,
     "role": request.role,
     "policy_name": request.policy_name,
     "precision_at_5": None,
     "recall": None,
     "metrics": {
       "included_count": trace.metrics.included_count,
       "total_tokens": trace.metrics.total_tokens,
       "avg_score": trace.metrics.avg_score,
       "avg_freshness_score": trace.metrics.avg_freshness_score,
       "blocked_count": trace.metrics.blocked_count,
       "stale_count": trace.metrics.stale_count,
       "dropped_count": trace.metrics.dropped_count,
       "budget_utilization": trace.metrics.budget_utilization
     },
     "doc_ids": {
       "included": [d.doc_id for d in trace.included],
       "blocked": [d.doc_id for d in trace.blocked_by_permission],
       "stale": [d.doc_id for d in trace.demoted_as_stale],
       "dropped": [d.doc_id for d in trace.dropped_by_budget]
     }
   }
   ```
5. Appends to `_session_audit`
6. The try/except catches any exception, logs a warning via `logging.getLogger(__name__).warning(...)`, and continues — `/query` still returns 200

**Why:** This is the core audit logging. Extraction must happen inside the lock to make ID assignment atomic with append. Fail-safe wrapping ensures audit bugs never break the query endpoint. Logging a warning (rather than silent swallow) ensures audit failures are observable in server logs without affecting the user-facing response.

**Acceptance criteria:**
- After a successful `/query`, `_session_audit` has one more entry
- Entry `id` follows `q{benchmark_count + live_index:03d}` pattern
- `precision_at_5` and `recall` are `None` (null in JSON)
- `created_at` is UTC ISO-8601
- If `result.trace` is `None` (shouldn't happen but defensive), audit is skipped with a warning log
- `/query` response body is unchanged — no new fields

**Files affected:** `src/main.py`

**Dependency:** T1

---

### T3 — Add GET /session-audit endpoint (P1)

**What to do:** Add a new route in `src/main.py`:
```python
@app.get("/session-audit")
def session_audit():
    with _session_audit_lock:
        entries = list(_session_audit)
    return {
        "session_started_at": _session_started_at,
        "benchmark_count": _BENCHMARK_COUNT,
        "entries": entries,
    }
```

Place it after `/evals` and before `/ingest`. Returns a snapshot copy under the lock.

**Why:** MET-B frontend needs a read endpoint. Returning a copy under the lock avoids mutation during serialization.

**Acceptance criteria:**
- `GET /session-audit` returns 200 with the documented shape
- Empty `entries` list when no queries have been made
- `session_started_at` is a valid UTC timestamp
- `benchmark_count` equals 12
- After N `/query` calls, `entries` has exactly N items

**Files affected:** `src/main.py`

**Dependency:** T1

---

### T4 — Add tests (P1)

**What to do:** Add tests to `tests/test_main.py`:

1. `test_session_audit_returns_200` — GET /session-audit returns 200 with required top-level keys
2. `test_session_audit_benchmark_count` — `benchmark_count` equals 12
3. `test_session_audit_id_starts_after_benchmark` — POST /query, then check first entry id == "q013"
4. `test_session_audit_id_increments` — POST /query twice, check ids are "q013" and "q014"
5. `test_session_audit_query_appends_one_entry` — POST /query, check len(entries) increases by exactly 1
6. `test_session_audit_compare_does_not_append` — POST /compare, check len(entries) unchanged
7. `test_session_audit_evals_does_not_append` — GET /evals, check len(entries) unchanged
8. `test_session_audit_entry_shape` — POST /query, verify entry has all required keys and correct types
9. `test_session_audit_live_entries_have_null_precision_recall` — entry has `precision_at_5: None` and `recall: None`

**Test isolation — critical:** Existing `/query` tests (e.g. `test_query_returns_200`, `test_query_respects_role_filtering`) will also append audit entries once MET-A is implemented. Delta-based counting is NOT sufficient for tests that assert specific IDs like "q013".

Add a test-only reset fixture that directly clears the module-level audit state:
```python
import src.main as _main_module

@pytest.fixture(autouse=False)
def reset_session_audit():
    """Reset the in-memory audit store so session-audit tests start clean."""
    with _main_module._session_audit_lock:
        _main_module._session_audit.clear()
    yield
    # No teardown needed — each test that uses this fixture gets a clean slate
```

Apply this fixture to all 9 session-audit tests. Do NOT add a public reset endpoint. Tests 3, 4, 5, 6, 7 depend on clean state for correct ID and count assertions. Tests 1 and 2 are read-only but benefit from consistency.

**Why:** Required by batch spec. These are the acceptance gates. The fixture ensures deterministic test results regardless of test execution order.

**Acceptance criteria:**
- All 9 tests pass
- No existing tests break (current: 175 passed)
- Session-audit tests use the `reset_session_audit` fixture

**Files affected:** `tests/test_main.py`

**Dependency:** T1, T2, T3

---

### T5 — Update CLAUDE.md (P2)

**What to do:** Add a subsection documenting `GET /session-audit` under the existing endpoint docs. Include: response shape, in-memory/ephemeral nature, benchmark_count derivation, demo caveat about globally shared log.

**Why:** CLAUDE.md is the project's living architecture doc.

**Acceptance criteria:** New subsection exists and matches implemented behavior.

**Files affected:** `CLAUDE.md`

**Dependency:** T2, T3

---

## Count Summary

P0=1, P1=3, P2=1, P3=0 — Total: 5 tasks

## Execution Order

T1 → T2 + T3 (parallel) → T4 → T5

## No-regression Constraints

- `/query` response contract unchanged (QueryResponse model, no new fields)
- `/compare` response contract unchanged
- `/evals` response contract unchanged — still benchmark-only
- Existing 175 tests must continue to pass
- `_evals_cache` pattern untouched

## Demo Caveats to Document

- Session audit is globally shared — all demo visitors see all queries from the current process lifetime
- In-memory only — data is lost on Render restart / redeploy
- This is by design for a demo; production would use persistent storage

## Verification Commands

```bash
# Run all tests (expect 175 + 9 new = 184 passed)
.venv/bin/python -m pytest tests/ -v

# Run only session-audit tests
.venv/bin/python -m pytest tests/test_main.py -k "session_audit" -v

# Manual smoke test
.venv/bin/python -m uvicorn src.main:app --reload &
curl -s http://localhost:8000/session-audit | python3 -m json.tool
curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{"query":"test","role":"analyst"}' > /dev/null
curl -s http://localhost:8000/session-audit | python3 -m json.tool
# Expect: 1 entry with id "q013"
```

## Docs to Update During Execution

- `CLAUDE.md` — add session-audit endpoint section (during T5, after implementation is verified)
- `docs/HANDOFF.md` — append MET-A session summary (after all tasks pass, as final execution step per batch protocol; must NOT be read or updated during preflight)
