# Phase 1: Naive foundation

- Build a naive `v0` on purpose and freeze it. Without a baseline there is no before and after, so resist "improving the prompt a little".
- Keep business rules in deterministic services and make each tool a thin wrapper. The rules stay testable without an LLM, and later asserts are cheap.
- Derive the prompt version from its content (a hash). Every trace can then name the exact prompt that ran, with no manual bumps to forget.
- Wire the endpoint and the UI end to end behind a seam with a fixed reply before adding the LLM. Plumbing bugs and agent bugs show up separately.
- A second LLM playing personas generates conversations at scale, but it grades a test written by the same author. Distrust its numbers.
- When a documented setting has no effect, read the code. The docs and the implementation can disagree.

## Links

- [PR #10: agent tools](https://github.com/matheusg18/fornada/pull/10)
- [PR #11: conversation endpoint](https://github.com/matheusg18/fornada/pull/11)
- [PR #13: attendant graph](https://github.com/matheusg18/fornada/pull/13)
- [PR #14: persona simulator](https://github.com/matheusg18/fornada/pull/14)
