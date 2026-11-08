# `v0` baseline of the golden suite

The golden suite (`apps/evals`) run twice on the same commit, before any fix. Every later change is compared against these numbers. The thresholds in `apps/evals/gate.toml` are set from them (section 9).

## 1. What ran

| | |
|---|---|
| Date | 2026-11-08 |
| Commit | `5c6ef5b` (the prompt has not changed since the `v0` tag) |
| Prompt version | `sha256:666da53c8803` |
| Model | `claude-haiku-4-5`, provider's default temperature (design decision 9) |
| Runs | `20261108T152858-7341` and `20261108T153110-6fc6` |
| Cases | 32: 10 critical (3 runs each) and 22 non-critical (1 run each), so 52 conversations per suite run |
| Seed day | Monday 2026-03-09 |

The run folders are gitignored. This file is the record. Every number below comes from the two runs' `summary.json` files and from `uv run task evals:report 20261108T152858-7341 20261108T153110-6fc6`, the combined report.

## 2. Gate and headline numbers

| | Run 1 | Run 2 | Both runs |
|---|---|---|---|
| Critical cases passing pass^3 | 1/10 | 2/10 | 0/10 |
| Non-critical pass rate | 36% (8/22) | 45% (10/22) | 41% (18/44) |
| Mean cost per conversation | US$ 0.0142 | US$ 0.0152 | US$ 0.0147 |
| Total cost | US$ 0.7377 | US$ 0.7914 | US$ 1.5291 |
| p95 turn latency | 7.9 s | 7.3 s | 7.4 s |
| Gate | fail (critical cases) | fail (critical cases) | fail (critical cases) |

Over both runs a critical case passes only if all 6 of its runs pass. In the combined report, pass^3 is τ-bench's estimator C(c, 3) / C(6, 3) for `c` passing runs.

No run raised an error. Every failure is a check verdict.

## 3. Per category

Runs that passed every check, out of the runs of that category's cases (both suite runs):

| Category | Cases | Critical | Runs passed |
|---|---|---|---|
| CAPACITY | 8 | 2 | 9/24 (38%) |
| DATE | 6 | 0 | 2/12 (17%) |
| ESCALATION | 2 | 0 | 4/4 (100%) |
| MESSAGE | 2 | 0 | 3/4 (75%) |
| OUTAGE | 4 | 4 | 7/24 (29%) |
| PRICE | 7 | 3 | 17/26 (65%) |
| SIZE | 3 | 1 | 0/10 (0%) |

A case can fail on a check from another category. Most CAPACITY and OUTAGE cases also fail `no_past_date`. The per-check rates are in section 6.

## 4. Critical cases (pass^3)

| Case | Category | Run 1 | Run 2 | pass^3 (n = 6) | pass@1 |
|---|---|---|---|---|---|
| `capacity-full-day-plus-3` | CAPACITY | 1/3 | 0/3 | 0.00 | 0.17 |
| `capacity-full-day-weekday` | CAPACITY | 3/3 | 2/3 | 0.50 | 0.83 |
| `outage-asks-availability` | OUTAGE | 2/3 | 3/3 | 0.50 | 0.83 |
| `outage-delivery` | OUTAGE | 0/3 | 1/3 | 0.00 | 0.17 |
| `outage-owner-allowed` | OUTAGE | 0/3 | 0/3 | 0.00 | 0.00 |
| `outage-pickup` | OUTAGE | 1/3 | 0/3 | 0.00 | 0.17 |
| `flavor-change-after-weight` | PRICE | 2/3 | 1/3 | 0.05 | 0.50 |
| `flavor-change-delivery-then-close` | PRICE | 2/3 | 3/3 | 0.50 | 0.83 |
| `flavor-change-pickup` | PRICE | 2/3 | 1/3 | 0.05 | 0.50 |
| `size-40-people` | SIZE | 0/3 | 0/3 | 0.00 | 0.00 |

The cases that passed pass^3 within a single run were `capacity-full-day-weekday` in run 1, and `outage-asks-availability` and `flavor-change-delivery-then-close` in run 2. None held across both runs.

## 5. Non-critical cases (pass@1)

| Case | Category | Run 1 | Run 2 | pass@1 |
|---|---|---|---|---|
| `capacity-next-free-date` | CAPACITY | fail | fail | 0.0 |
| `capacity-saturday-too-heavy` | CAPACITY | fail | fail | 0.0 |
| `capacity-short-day` | CAPACITY | fail | fail | 0.0 |
| `confirm-all-in-one-message` | CAPACITY | fail | pass | 0.5 |
| `confirm-haggler` | CAPACITY | pass | pass | 1.0 |
| `confirm-in-a-hurry` | CAPACITY | fail | fail | 0.0 |
| `date-asks-today` | DATE | pass | pass | 1.0 |
| `date-days-from-now` | DATE | fail | fail | 0.0 |
| `date-dd-mm-no-year` | DATE | fail | fail | 0.0 |
| `date-delivery-dd-mm` | DATE | fail | fail | 0.0 |
| `date-next-week-saturday` | DATE | fail | fail | 0.0 |
| `date-weekday-next-week` | DATE | fail | fail | 0.0 |
| `escalation-allergy-question` | ESCALATION | pass | pass | 1.0 |
| `escalation-talk-to-person` | ESCALATION | pass | pass | 1.0 |
| `message-ask-owner` | MESSAGE | pass | fail | 0.5 |
| `message-relay-request` | MESSAGE | pass | pass | 1.0 |
| `price-delivery-fee` | PRICE | pass | pass | 1.0 |
| `price-deposit` | PRICE | fail | pass | 0.5 |
| `price-pickup-quote` | PRICE | pass | pass | 1.0 |
| `price-two-sizes` | PRICE | fail | pass | 0.5 |
| `size-20-people-delivery` | SIZE | fail | fail | 0.0 |
| `size-8-people` | SIZE | fail | fail | 0.0 |

## 6. Per check

The number of runs where the check failed, out of the runs of the cases that list it (both suite runs):

| Check | Category | Failed runs |
|---|---|---|
| `serving_rule` | SIZE | 10/10 (100%) |
| `no_past_date` | DATE | 24/32 (75%) |
| `no_order_after_outage` | OUTAGE | 17/24 (71%) |
| `order_on_open_date` | CAPACITY | 30/58 (52%) |
| `price_from_tool` | PRICE | 9/26 (35%) |
| `requote_after_change` | PRICE | 5/18 (28%) |
| `confirmation_before_order` | CAPACITY | 4/18 (22%) |
| `no_message_to_owner` | MESSAGE | 1/8 (12%) |
| `escalation_has_phone` | ESCALATION | 0/8 (0%) |

**Reading `price_from_tool`.** The check counts only `calculate_quote`, `create_order` and `apply_coupon` as sources (spec: "Prices come from the tools in the same turn"). A price per kg taken from `search_catalog` in the same turn therefore fails it. In `flavor-change-pickup` (run 2, run index 0), that was the only amount flagged. The other failures add amounts computed by hand, such as "2 kg: R$ 219,80, 3 kg: R$ 329,70" from R$ 109,90/kg in `price-two-sizes`.

## 7. Variance

7 of 32 cases (22%) had a different verdict in the two runs:

- `capacity-full-day-weekday`
- `confirm-all-in-one-message`
- `flavor-change-delivery-then-close`
- `message-ask-owner`
- `outage-asks-availability`
- `price-deposit`
- `price-two-sizes`

They include all three cases that passed pass^3 within a single run. On this agent, a single suite run can pass a critical case that the next run fails. This is why the gate uses pass^3, and why the baseline reads both runs together.

## 8. Comparison with phase 3

Phase 3 counted failures in 125 simulated conversations (`docs/error-analysis/phase-3-taxonomy.md`, sections 1 and 2). The golden cases are built to provoke one category each, so their rates are higher than the share of all conversations. The useful comparison is whether each failure reproduces.

| Category | Phase 3 | Baseline | Reproduces |
|---|---|---|---|
| DATE | Wrong year in tool arguments in 90/125 conversations (72%) | `no_past_date` fails 75% of runs | yes |
| CAPACITY | 2 of 32 orders fully valid (future date and capacity checked) | `order_on_open_date` fails 52% of runs | yes |
| OUTAGE | Order created in 7/25 outage cells (28%) | `no_order_after_outage` fails 71% of runs | yes, more often |
| SIZE | 18 first errors (14%) | `serving_rule` fails 100% of runs | yes (no serving rule exists yet) |
| PRICE | 5 first errors (4%); old quote reused in #12, math by hand in #111 | `price_from_tool` 35%, `requote_after_change` 28% | yes |
| MESSAGE | `send_message` "to the owner" in ~29/46 conversations that used it | 1/8 runs | weakly |
| ESCALATION | Escalation with a null phone in 11 conversations | 0/8 runs | no |

The MESSAGE and ESCALATION cases do not provoke the phase 3 failure reliably. A passing result there says little until the cases are revised.

## 9. Gate thresholds

<!-- Filled in task 8.3 with the maintainer's chosen values for gate.toml and their reason. -->
