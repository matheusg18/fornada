# fornada-api

FastAPI service that runs the LangGraph ordering agent.

## Configuration

Settings come from environment variables and the `.env` file at the repo root
(the environment wins). Copy `.env.example` to `.env` and fill in an API key.
Run every command from the repo root so `.env` is found.

Nested settings use a double underscore, `NAMESPACE__FIELD`:

| Variable | Default | Meaning |
|---|---|---|
| `LLM__PROVIDER` | `anthropic` | Active provider: `anthropic` or `openai` |
| `LLM__ANTHROPIC__API_KEY` / `LLM__ANTHROPIC__MODEL` | – / `claude-haiku-4-5` | Required when Anthropic is active |
| `LLM__OPENAI__API_KEY` / `LLM__OPENAI__MODEL` | – / `gpt-5-mini` | Required when OpenAI is active |
| `APP__TIMEZONE` | `America/Sao_Paulo` | IANA time zone for "now" and dates |
| `LOG__LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

Startup fails with a `ConfigError` that names the offending variable.

Logs are JSON, one object per line on stdout, with `timestamp` (UTC),
`level`, `logger` and `message`, plus any `extra` fields:

```bash
LLM__ANTHROPIC__API_KEY=sk-ant-test uv run --package fornada-api fornada-api
uv run --package fornada-api pytest
```
