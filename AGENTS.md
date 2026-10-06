# AGENTS.md

Guidance for AI coding agents working in this repository. Claude Code reads this file natively because there is no `CLAUDE.md`. Do not create one.

## Project

**Fornada** is an AI chatbot for the customers of a fictional bakery (confeitaria). It is a study and portfolio project published on GitHub. The bot's end users speak Brazilian Portuguese.

Planned stack (no application code yet):

- **API:** FastAPI (Python, managed with `uv`)
- **Agent:** LangChain + LangGraph
- **Observability:** Langfuse (tracing, prompt management, evals)
- **Database:** PostgreSQL (app data and the LangGraph checkpointer)

## Workflow

- **Spec-driven development with OpenSpec.** Non-trivial changes start as an OpenSpec change: `/opsx:propose` → review → `/opsx:apply` → `/opsx:archive`. Specs live in `openspec/specs/`, and in-flight changes live in `openspec/changes/`. Write all OpenSpec artifacts in English (see `openspec/config.yaml`).
- **Small steps.** Before each step, announce it and wait for the maintainer's approval. Make one commit per step.
- **Commits.** Use Conventional Commits prefixes (`feat:`, `fix:`, `chore:`, `docs:`…) and write the message in Portuguese.

## Agent tooling

Everything is installed at project scope and versioned:

- `.claude/settings.json` declares the marketplaces and enabled plugins.
- `.mcp.json` declares the MCP servers.
- `.claude/skills/` holds the skills copied into the repo.

| Area | Resource | Type | Source | Use it when… |
|---|---|---|---|---|
| Specs | `openspec-*` skills, `/opsx:*` commands | skills/commands | `@fission-ai/openspec@1.14.1 init --tools claude` | planning or implementing any change |
| FastAPI | `fastapi` | skill | `fastapi/fastapi` via `npx skills` (`skills-lock.json`) | writing endpoints, dependencies, Pydantic models, SSE streaming |
| LangChain / LangGraph | `langchain-skills` | plugin | marketplace `langchain-ai/langchain-skills` | writing agents, graphs, persistence, human-in-the-loop, RAG |
| LangChain / LangGraph | `docs-langchain` | MCP (HTTP) | `https://docs.langchain.com/mcp` | checking current LangChain/LangGraph APIs |
| Langfuse | `langfuse` | plugin | `claude-plugins-official` | instrumenting tracing, prompts, datasets, evals |
| Langfuse | `langfuse-docs` | MCP (HTTP) | `https://langfuse.com/api/mcp` | checking Langfuse docs |
| PostgreSQL | `postgres-best-practices` | plugin | marketplace `supabase/agent-skills` | schema design, migrations, indexes, query tuning |
| PostgreSQL | `postgres` | MCP (stdio) | `uvx postgres-mcp --access-mode=restricted` | inspecting the database, EXPLAIN plans, health checks |
| Docs (general) | `context7` | plugin (MCP) | `claude-plugins-official` | up-to-date docs for any other library |
| Browser / E2E | `playwright` | plugin (MCP) | `claude-plugins-official` | driving a browser, end-to-end tests |

Notes:

- The `postgres` MCP reads `DATABASE_URI` from the environment. It only works once a database exists. Never commit credentials; put them in `.env`, which is gitignored.
- The `postgres-best-practices` plugin bundles a Supabase docs MCP. It is disabled via `disabledMcpServers` in `.claude/settings.json` because this project does not use Supabase.

### Installing new agent resources

Follow this order:

1. Look for a **Claude Code plugin/marketplace**: the vendor's own marketplace or `claude-plugins-official`. Install it with `claude plugin install <plugin>@<marketplace> --scope project`.
2. If none exists, fall back to **`npx skills add <repo> --skill <name> --agent claude-code --copy`**, so the files are copied into `.claude/skills/` and pinned in `skills-lock.json`.
3. For a standalone MCP server, use **`claude mcp add --scope project …`**.

Do not use Microsoft APM. This project only targets Claude Code.
