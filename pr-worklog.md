# PR Worklog

## 2026-10-29 — agno-agi/agno #11341

**Repo:** `agno-agi/agno` (upstream `main` @ `4973add19c00342b28a1d1d984085929eb3361b4`, v3.1.11)

**Issue:** [#11341 — [Bug] Session token and cost totals double-count a paused and resumed run](https://github.com/agno-agi/agno/issues/11341)

**Gate:** GATED. `.github/pull_request_template.md` requires external contributors to link an issue that has the `ready` label; `CONTRIBUTING.md` and `.github/workflows/pr-triage.yml` auto-close external PRs whose linked issue is not triaged with `ready`. The issue carries no labels, and the token owner has only `pull` permission on the repo (no write/triage), so the label cannot be added locally.

**Action:** No PR opened. Left a comment on the issue with the root cause, fix and verification instead: https://github.com/agno-agi/agno/issues/11341#issuecomment-6486581630

**Fix:** `update_session_metrics()` in `libs/agno/agno/agent/_storage.py` now reads the already-stored run row for the same `run_id` (`db.get_run`) and accumulates only the delta of the live `RunMetrics` (counters, cost, per-model `details`, `additional_metrics`) instead of the full cumulative totals. Added async twin `aupdate_session_metrics` and wired it into `apersist_run_in_session` so `arun`/`acontinue_run` behave the same.

**Files:**
- `libs/agno/agno/agent/_storage.py`
- `libs/agno/agno/agent/_session.py`
- `libs/agno/agno/agent/_run.py`
- `libs/agno/tests/unit/agent/test_session_metrics_once.py` (new)

**Verification:**
- Before fix: `3 failed, 1 passed` (sync pause+resume, async pause+resume and `checkpoint="tool-batch"` fail; separate runs pass)
- After fix: `4 passed` in `test_session_metrics_once.py`
- Related suite `tests/unit/agent`: 1138 passed, 1 pre-existing unrelated failure (`test_field_type_serializes_for_every_annotation_form[Union-typing.Optional[int]]`, Python 3.14 annotation rendering)
- `ruff format` / `ruff check` / import-sort pass; `mypy` reports no errors in the changed files

---
