# Fornada

A chat agent that takes cake orders for a fictional bakery, built to be broken.

The agent itself is deliberately simple. The real work is everything around it: telemetry, error analysis, evals gated in CI, red teaming, guardrails and governance. Every improvement is measured against a naive `v0`, so the end result is a set of before/after numbers for reliability, security, cost and latency.

> **Status:** early setup. No application code yet.

## Why a bakery

Ordering a cake looks trivial, which is the point. The agent is easy to build and fails in measurable ways:

- **Verifiable rules:** price per kg, minimum lead time, daily oven capacity, delivery fees by neighborhood.
- **Third-party data:** other customers' names, phones and addresses.
- **Untrusted input:** free-text messages and a "reference photo description" that lands in the context, an opening for prompt injection.
- **Side-effecting actions:** creating and cancelling orders, applying coupons, sending messages.

The bot talks to customers in Brazilian Portuguese. Its tools are `search_catalog`, `check_capacity`, `calculate_quote`, `create_order`, `get_order`, `cancel_order`, `apply_coupon`, `send_message` and `escalate_to_human`.

## Stack

| Layer | Choice |
|---|---|
| Agent | Python, LangGraph, FastAPI |
| Data | PostgreSQL (Docker, seeded with fake data) |
| Telemetry | OpenTelemetry SDK → EDOT Collector → Langfuse and Elasticsearch/Kibana |
| Evals | DeepEval + pytest, gated in GitHub Actions |
| Red team | promptfoo + hand-written attacks |
| Guardrails | Deterministic policies as LangGraph nodes; Model Armor vs. Prompt Guard 2 |
| PII | Microsoft Presidio (pt-BR) |

## Roadmap

1. Naive foundation (`v0`)
2. Instrumentation
3. Error analysis
4. Evals and CI gate
5. Red team
6. Guardrails and online evals
7. Governance

## Development

Work is spec-driven with [OpenSpec](https://github.com/Fission-AI/OpenSpec). The full project context, the challenge rules and the AI agent tooling are documented in [AGENTS.md](AGENTS.md).
