# Prototype Audit — October 2026

Scope: the existing PAMM platform source (FastAPI backend + React/Vite frontend), audited and
upgraded into a demonstrable prototype. This document records what was found, what changed,
and what remains. Status labels:

| Label | Meaning |
|---|---|
| **CONFIRMED** | Verified by reading the code **and** running it (tests, API calls or the browser) |
| **PARTIAL** | Some functionality exists; the complete workflow does not |
| **MOCKED** | Works, but driven by simulated or seeded data |
| **BROKEN** | Existed but did not work correctly (fixed items are marked *fixed*) |
| **MISSING** | No meaningful implementation |
| **PROPOSED** | Recommended future work |

## 1. Architecture (as found)

- **Backend** — FastAPI 0.115, SQLAlchemy 2, Alembic (3 migrations), Pydantic v2, python-jose JWT,
  passlib/bcrypt. Postgres is the intended database; Redis Streams for the event outbox
  (fakeredis supported for dev). Decimal-only accounting in `app/domain/pamm.py`.
- **Domain modules** — PAMM unit/NAV engine, three P&L allocation methods (euro-days, start
  capital, end capital), HWM performance fees, Merkle settlement proofs, hash-chained audit log,
  risk rules, MAM order split, copy trading, settlement sagas with compensation, LP-based
  risk-constrained allocation (scipy), latency/slippage prediction, transactional outbox.
- **Broker adapters** — `simulated` (working), `mt5`, `ctrader`, `crypto` (real SDK integrations
  that run only when SDK + credentials are present; otherwise BLOCKED).
- **Frontend** — React 18, React Router 6, TanStack Query 5, Recharts 3, Tailwind 3. 17 pages,
  role-filtered sidebar. JWT stored in `localStorage`.
- **Deployment** — docker-compose (postgres, redis, backend, frontend dev server), Helm chart,
  k8s secret template, backup/restore scripts.
- **Tests** — 115 pytest tests across domain logic, API, tenant isolation, idempotency, sagas,
  outbox, Redis streams and backup/restore.

## 2. Baseline (before changes)

| Check | Result |
|---|---|
| Frontend `tsc -b` + `vite build` | Passed (bundle 732 kB, size warning) |
| Backend import | Passed after installing `requirements.txt` |
| Backend tests (no Postgres) | 65 passed, 10 failed, 35 errors — all DB/Postgres related |
| Run locally | **Blocked**: `.env` pointed at a Linux socket (`/home/z/my-project/pgdata`) from the original build sandbox |
| Docker | Docker Desktop could not be started on this machine; compose not verified |
| Demo data | Seed created users and empty masters only — every dashboard and chart was empty |

## 3. Findings and fixes

### P0 — integrity and security

| # | Finding | Status |
|---|---|---|
| 1 | **Investor could subscribe using another investor's trading account.** `POST /subscriptions` checked tenant but not account ownership. | BROKEN → *fixed* (403 unless `owner_user_id` matches) — `routers/investor.py` |
| 2 | **`GET /investors` returned every account in the tenant to investors.** | BROKEN → *fixed* (investors see only their own) |
| 3 | **`GET /rollovers/{id}` exposed all investors' entries** (login, P&L share, fees) to any investor in the tenant. | BROKEN → *fixed* (investors receive only their own entries) — `routers/rollover.py` |
| 4 | **Unauthenticated `/api/public/*` aggregated all tenants**, leaking one broker's book on another's public page. | BROKEN → *fixed* (scoped to `DEFAULT_TENANT`) — `routers/public.py` |
| 5 | Weak default `JWT_SECRET` accepted in any environment. | *fixed* — startup refuses weak/short secrets when `ENVIRONMENT=production` — `config.py` |
| 6 | CORS origins hard-coded. | *fixed* — `CORS_ORIGINS` env var |
| 7 | No `.gitignore`; `.env` files, local DB, venv, `node_modules`, `dist` would be committed. Docker build contexts would copy `.env`/`.venv` into images. | *fixed* — `.gitignore`, `backend/.dockerignore`, `frontend/.dockerignore` |
| 8 | A failed login (401) triggered the global "session expired" redirect, so the error was never shown. | BROKEN → *fixed* — `api.ts` |
| 9 | `AuditLog.id` (`BigInteger` autoincrement) fails on SQLite. | *fixed* with a SQLite type variant; Postgres unchanged — `models.py` |

Regression tests for 1–4 and the rollover P&L fix: `backend/tests/test_prototype_fixes.py`.

### Data correctness

| # | Finding | Status |
|---|---|---|
| 10 | Rollovers stored `master_pnl = 0` and `master_equity_after = equity_before`, so every "cumulative P&L" chart was flat. | BROKEN → *fixed* — P&L = sum of allocated shares, equity-after = post-fee equity. Allocation and fee rules unchanged. |
| 11 | `/public/top-accounts` had no `strategy_id`, so the homepage "Invest" button submitted `undefined`. | BROKEN → *fixed* |
| 12 | Home "Invest" used the first investor account in the tenant (combined with #2, often someone else's). | BROKEN → *fixed* — explicit funding-account picker of the user's own accounts |
| 13 | Rollover history ordered by insert time and capped at 30. | *fixed* — ordered by `period_end`, cap 120 |

### P1 — visual quality / UX

| # | Finding | Status |
|---|---|---|
| 14 | Mixed Persian/English UI with no RTL handling (`lang="en"`, Persian titles, English tables). | *fixed* — standardised on English (13 of 17 pages were already English; README/portfolio audience). See §6. |
| 15 | No design system: ad-hoc slate colours, light-mode text on dark cards, raw decimals (`129.14493078918160362166…`), raw enum values (`euro_days`), UUIDs in UI. | *fixed* — token-based theme (light + dark), Inter/JetBrains Mono, tabular numerals, shared formatters (`format.ts`) and components (`components/ui.tsx`) |
| 16 | Empty dashboards and charts. | *fixed* — seeded 26-week **simulated** history (§4) |
| 17 | Managers page "invest" link pointed to `/#invest` (dead anchor). | BROKEN → *fixed* — links to strategy detail |
| 18 | Settlement page required pasting a subscription UUID. | *fixed* — master → rollover → entry pickers |
| 19 | No route guard: any role could open any URL. | *fixed* — `RoleGate` mirrors sidebar roles (API still authoritative) |
| 20 | No mobile layout; sidebar fixed 256 px. | *fixed* — drawer below `lg`, horizontal-scroll tables, verified at 375 px with no page overflow |
| 21 | Forms had no validation; errors surfaced as raw JSON; `alert()` used. | *fixed* — field validation, readable errors, toasts |
| 22 | Recharts entry animation stalls when the tab is throttled (charts appeared empty in screenshots/background tabs). | *fixed* — animation disabled on primary charts |

### Portability

| # | Finding | Status |
|---|---|---|
| 23 | `test_backup_restore.py` hard-coded `/home/z/my-project/...`. | *fixed* — repo-relative paths; `BACKUP_TEST_PG_HOST/PORT` env vars (defaults keep the original socket) |
| 24 | `scripts/run_m*_acceptance.sh`, `scripts/m4_load_tests.py`, `scripts/m5_acceptance.py` hard-code the same sandbox path. | **Not changed** — documented; PROPOSED |
| 25 | Vite proxy hard-coded to `localhost:8000`; compose set an unused `VITE_API_BASE`. Inside the frontend container the proxy hit itself. | BROKEN → *fixed* — `VITE_API_PROXY` (compose sets `http://backend:8000`). **Not verified in Docker** (daemon unavailable). |
| 26 | `fakeredis` required by tests but missing from `requirements.txt`. | *fixed* |

## 4. Demo data

`python -m app.seed` now also runs `app/demo_history.py` (disable with `SEED_DEMO_HISTORY=0`).
It creates 3 managers, 6 masters/strategies, 6 investors with their own accounts and 13
subscriptions, then drives **the real API** through 26 weekly cycles of *simulated P&L →
rollover*. NAV, fees, HWM, Merkle roots and the audit chain therefore come from production code
paths; only the P&L input is a seeded random walk, and timestamps are back-dated afterwards.
The UI labels this data as simulated on every performance view and in the footer.

## 5. Feature status

| Area | Status | Notes |
|---|---|---|
| Auth (JWT login, roles, tenant scoping) | CONFIRMED | Refresh endpoint exists but the frontend does not use it (re-login after 60 min) — PARTIAL |
| PAMM units/NAV, subscriptions | CONFIRMED | |
| Rollover (3 allocation methods, HWM fees) | CONFIRMED | |
| Merkle settlement proofs + statements | CONFIRMED | verified in browser |
| Hash-chained audit log | CONFIRMED | |
| Risk rules (exposure, drawdown) | CONFIRMED | tests |
| Strategy marketplace, detail, managers | CONFIRMED / MOCKED data | |
| Broker / investor / manager dashboards | CONFIRMED / MOCKED data | |
| MAM split | CONFIRMED (tests) | no seeded MAM orders — screen starts empty |
| Copy trading | CONFIRMED (tests) | no seeded followers — screen starts empty |
| Settlement sagas, LP allocation, latency model, outbox | CONFIRMED (tests) | technical consoles, little seeded data |
| Broker adapters MT5 / cTrader / crypto | PARTIAL | code present; BLOCKED without SDK + credentials; never tested live here |
| Live market data, real positions, open trades | MISSING | P&L is applied directly to master equity |
| Deposits / withdrawals / wallet | MISSING | labelled in UI |
| Notifications, activity feed | MISSING | |
| Login rate-limiting, MFA, password reset | MISSING | |
| KYC / onboarding, user management UI | MISSING | |

## 6. Assumptions and decisions

- **English UI.** The original was mostly English with Persian on four screens and no RTL support.
  Mixed-direction text without RTL layout looked broken, so the prototype standardises on English.
  A proper fa/en i18n with RTL is PROPOSED.
- **SQLite demo mode.** Postgres remains the production database; SQLite (`DATABASE_URL=sqlite:///…`)
  is used for the zero-dependency local demo. The full test suite was run against real Postgres.
- **Financial logic untouched.** No allocation, fee or NAV rule was changed. Client-side derived
  metrics (max drawdown, period return) are computed from the API's NAV series and labelled.

## 7. Verification performed

| Check | Result |
|---|---|
| Backend tests on Postgres 16 (embedded via `pgserver`) + fakeredis | **114 passed, 5 skipped** (skips need a real `redis-server`) |
| Frontend `tsc -b` and `vite build` | Passed (780 kB JS, chunk-size warning) |
| Seed + demo history on SQLite and on Postgres | Passed |
| Browser walkthrough (built-in browser, 1440 px, 375 px, light + dark) | Login (valid + invalid), marketplace sort/filter/search, strategy detail + range selector, allocation modal (validation + successful subscription), portfolio, broker dashboard, managers, master accounts, investors, rollovers, settlement proof verification, MAM, copy, sagas, adapters, role-gated route |
| Docker Compose build/run | **Not verified** — Docker Desktop daemon would not start on this machine |
| Real Redis tests | **Not run** — no `redis-server` available |

## 8. Recommended next steps (PROPOSED)

1. Use the refresh token in the frontend; move tokens to httpOnly cookies.
2. Add login rate limiting and account lockout.
3. Seed MAM orders and copy followers so those consoles demo well.
4. Code-split the frontend (route-level `lazy()`); the bundle is 780 kB.
5. Replace remaining hard-coded `/home/z/...` paths in `scripts/`.
6. Production frontend image (static build behind nginx) instead of the Vite dev server.
7. fa/en internationalisation with RTL.
8. Verify the compose stack end-to-end once Docker is available.
