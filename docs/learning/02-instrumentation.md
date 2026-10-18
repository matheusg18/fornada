# Phase 2: Instrumentation

- Write the GenAI spans by hand instead of using an auto-instrumentation library. The libraries trace the framework's internals (every runnable, chain and hook), add vendor attributes, and often capture prompts by default.
- OTel GenAI semantic conventions are still moving. Keep the attribute names in one constants module, noting the semconv version they came from, so a bump is one diff.
- One trace per turn, with the conversation as a session. A trace that stays open for a whole conversation loses its root when the process dies.
- Global instrumentors trace more than you meant to: an HTTP client instrumentor also traces the LLM SDK's calls, and a framework that uses the global provider traces a websocket for as long as the tab is open. Instrument the one client or connection you care about.
- Put PII handling in the Collector, not in every app. One receiver can feed two pipelines: full content for the LLM view, redacted for the general observability store.
- Redact before any processor that derives data. Otherwise the content leaks into derived fields and metrics.
- Hash phone numbers with a salt. The space of possible numbers is small enough to brute-force an unsalted hash.
- Fail closed: a redaction error should drop the data, not let it through.
- Redaction that covers attributes misses span events. Exception messages and stack traces carry the same data and need their own rule.
- Database errors leak row values through the server's detail line, even with bound parameters hidden.
- Metric dimensions get an allowlist. Never an id, a phone or a message: they leak data and blow up cardinality.
- An allowlist that strips an attribute merges series. The backend can then reject the duplicates while the exporter still counts them as sent, so check the logs, not only the counters.
- Histogram sums are approximations. Take percentiles from them, but take totals (tokens) from the raw counts. Cost as a counter matched exactly.
- Watch the denominator in "cost per conversation": a conversation is counted once, but it costs on every turn. Use running sums.
- Baggage crosses process boundaries and can reach third parties. Read the entry you need, then clear it before the next outgoing call.
- Give JVM services a hard memory limit, no swap and an explicit heap. With swap they get slow without failing; without a limit they take the machine.
- Measure memory before choosing a limit. Estimates were off by half: a "1 GiB" Elasticsearch was OOM-killed within minutes.
- Fault injection (chaos mode) must be visible in the trace. Otherwise an injected error looks like a real bug during error analysis.
- Verify each signal end to end with a synthetic sender (`telemetrygen`) and the Collector's own counters before blaming the app.
- Dashboards are code: export them, commit them and import them on start, or a UI edit is lost.

## Links

- [PR #16: app tracing](https://github.com/matheusg18/fornada/pull/16)
- [PR #18: agent spans](https://github.com/matheusg18/fornada/pull/18)
- [PR #20: Elastic stack](https://github.com/matheusg18/fornada/pull/20)
- [PR #24: redacted Elastic traces](https://github.com/matheusg18/fornada/pull/24)
- [PR #25: correlated logs](https://github.com/matheusg18/fornada/pull/25)
- [PR #28: app metrics](https://github.com/matheusg18/fornada/pull/28)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
