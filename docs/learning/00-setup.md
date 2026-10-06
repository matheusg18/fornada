# Phase 0: Setup

- Prepare the ground before any code: AGENTS.md, a dev container, and agent tooling (skills, plugins, MCPs).
- Install agent tooling at project scope and version it in the repo, not in user-level config.
- Let the tools install dependencies (`uv add`, `npm install`) so they resolve the latest version. Never hand-write versions.
- Container images are the exception: pin the exact version and let Dependabot bump it.
- Make the agent follow each library's official getting started (docs MCPs, Context7), not its training memory.
- The dev container is the agent's jail. Full permissions only inside it; no Docker socket; no `~/.ssh` mount, only SSH agent forwarding.
- Keep two env files: dev-environment secrets and app settings have different consumers.
- Test risky choices in an isolated worktree first, like a new Python version or a dependency bump, before adopting them.
- Use a uv workspace for a monorepo: one lockfile and one `.venv` at the root.
- Talk to the agent in your own language; keep the repo in English.
- Work in small steps with approval: one commit per step, and never rewrite history.

## Links

- [PR #1: dev container](https://github.com/matheusg18/fornada/pull/1)
- [PR #2: uv workspace](https://github.com/matheusg18/fornada/pull/2)
