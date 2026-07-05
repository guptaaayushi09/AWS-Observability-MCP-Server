# AWS Observability MCP Server — Build Spec

> A remote, OAuth-secured MCP server that exposes an AWS CloudWatch + ECS observability stack
> to any LLM agent, enabling natural-language incident investigation.
>
> **This file is the working brief for Claude Code.** It contains the full design, tool
> specs, testing strategy, and a phased build plan. Build it phase by phase, committing at
> each milestone.

---

## 1. What this is (one line)

A server that wraps an AWS monitoring stack (CloudWatch metrics, CloudWatch Logs, alarms, ECS
service health) into a small set of **typed MCP tools** that any LLM agent — Claude Desktop, a
custom LangGraph agent, the MCP Inspector — can call over a standard protocol, without ever
touching `boto3` or AWS credentials directly.

## 2. The problem it solves

On-call incident investigation today means manually context-switching across the CloudWatch
console, Logs Insights, alarm history, and ECS service status, then correlating timestamps by
hand under pressure. An LLM can do that correlation in seconds **if** it has safe, structured,
permission-scoped access to the data. MCP is the contract that provides exactly that.

Target interaction:

> "Why is the checkout service throwing 5xxs in the last 15 minutes?"

The agent autonomously calls `query_cloudwatch_metrics` → `tail_logs` → `list_recent_alarms`,
correlates the results, and returns a root-cause summary.

## 3. Differentiation (read this — it shapes the whole project)

AWS already ships an **open-source CloudWatch MCP server** (`awslabs/mcp`) and a managed AWS MCP
Server. So a from-scratch clone is *not* the goal. Two facts create the gap this project fills:

1. The official `awslabs` CloudWatch MCP server **runs locally only** (same host as the LLM client).
2. The managed AWS MCP Server uses **IAM + SigV4 via a local proxy, not OAuth**.

**This project's value = productionizing a local observability MCP server into a secure, remote,
multi-tenant service.** That means: Streamable HTTP transport, OAuth 2.1 auth, tool-level RBAC,
result truncation for context budget, and a scale-to-zero deployment.

> Use the official `awslabs/mcp` CloudWatch server as a **reference** for tool shapes and naming.
> Do not copy it; build the remote + auth + deploy layer it does not provide.

Resume framing: *"Productionized a local observability MCP server into a secure remote
multi-tenant service on a scale-to-zero deployment, with OAuth 2.1, tool-level RBAC, and
OpenTelemetry tracing."*

---

## 4. Architecture

```
┌────────────────────────────────────────────────────────────┐
│  LLM AGENT  (Claude Desktop · MCP Inspector · LangGraph)    │
│  - discovers tools via list_tools, composes calls per query │
└───────────────────────────┬────────────────────────────────┘
                            │  OAuth 2.1 bearer token (PKCE)
                            │  Streamable HTTP
                            ▼
┌────────────────────────────────────────────────────────────┐
│  AUTH + TRANSPORT LAYER                                     │
│  - validates token + scopes BEFORE any tool runs           │
│  - /.well-known/oauth-protected-resource discovery         │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│  MCP SERVER CORE  (FastMCP)                                │
│  Tools:  get_service_health · query_cloudwatch_metrics ·   │
│          tail_logs · list_recent_alarms · summarize_incident│
│  Cross-cutting: result truncation, optional Redis TTL cache,│
│                 OpenTelemetry spans per tool call          │
└───────────────────────────┬────────────────────────────────┘
                            │  boto3 (read-only IAM role)
                            ▼
┌────────────────────────────────────────────────────────────┐
│  AWS APIs                                                   │
│  ECS DescribeServices · CloudWatch GetMetricData ·         │
│  CloudWatch Logs (FilterLogEvents / Insights) ·            │
│  CloudWatch DescribeAlarms                                 │
└────────────────────────────────────────────────────────────┘
```

Key idea: you expose the **building blocks** (tools); the LLM writes the orchestration on the
fly per question. The `summarize_incident` composite tool is the "do it all in one call" path.

---

## 5. Tech stack

| Concern        | Choice                                                          |
|----------------|----------------------------------------------------------------|
| Language       | Python 3.12                                                    |
| MCP framework  | `fastmcp` (pin the version in `requirements.txt`)             |
| AWS SDK        | `boto3`                                                        |
| Schemas        | Pydantic models for tool inputs/outputs                       |
| Transport      | stdio (dev) → Streamable HTTP (prod)                          |
| Auth           | OAuth 2.1 with PKCE (FastMCP built-in provider)               |
| Testing        | `pytest` + `moto` (`@mock_aws`); LocalStack for end-to-end    |
| Cache (opt.)   | Redis, short-TTL on expensive metric queries                 |
| Tracing (opt.) | OpenTelemetry                                                  |
| Deploy         | Docker → scale-to-zero target (Lambda container URL / Cloud Run) |

> Spec note: MCP is evolving toward stateless horizontal scaling and there are breaking changes
> in flight. **Pin `fastmcp` and `mcp` versions** and record them in the README so the repo runs
> reproducibly later.

---

## 6. Tool specifications

All tools are **read-only** (`readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true`, `openWorldHint: true`). Use Pydantic for input + output schemas. Every
tool must **truncate / pre-summarize** large payloads before returning (see §7). Error messages
must be actionable (tell the agent what to try next).

### 6.1 `get_service_health`
- **AWS call:** ECS `DescribeServices`
- **Input:** `service_name: str`, `cluster: str | None = None`
- **Returns:** running vs desired task count, deployment rollout status, last N service events
- **Purpose:** "is the service itself healthy / mid-deploy?"

### 6.2 `query_cloudwatch_metrics`
- **AWS call:** CloudWatch `GetMetricData`
- **Input:** `namespace: str`, `metric_name: str`, `dimensions: list[dict]`,
  `stat: str = "Average"`, `period_seconds: int = 60`,
  `start_time: datetime`, `end_time: datetime`
- **Returns:** summarized stats (p50 / p95 / max / latest) **plus a truncated datapoint sample**,
  not the full series
- **Note:** `GetMetricData` can return up to ~100k datapoints — never return them raw.

### 6.3 `tail_logs`
- **AWS call:** CloudWatch Logs `FilterLogEvents` (or `StartQuery` + `GetQueryResults` for Insights)
- **Input:** `log_group: str`, `filter_pattern: str | None = None`,
  `start_time: datetime`, `end_time: datetime`, `limit: int = 50`
- **Returns:** top matching lines + a detected **error-pattern summary** (group similar errors,
  show counts), truncated to a token-safe size

### 6.4 `list_recent_alarms`
- **AWS call:** CloudWatch `DescribeAlarms`
- **Input:** `state: str = "ALARM"`, `max_records: int = 25`
- **Returns:** alarms in the requested state with their metric, threshold, and state-change time

### 6.5 `summarize_incident` (composite — the showcase tool)
- **Orchestrates:** fans out to `list_recent_alarms` → `query_cloudwatch_metrics` → `tail_logs`
  (+ `get_service_health`) for a time window, correlates them, returns a structured digest.
- **Input:** `service_name: str`, `time_window_minutes: int = 30`
- **Returns:** `{ summary, firing_alarms[], key_metrics[], top_errors[], likely_cause }`
- This is the "pager fires → auto-summary" path and the strongest demo moment.

---

## 7. Production design decisions (the senior signal)

1. **Read/write separation + scoped tokens.** All tools here are read-only. If a write tool is
   ever added, it requires a *different* OAuth scope (confused-deputy defense / tool-level RBAC).
2. **Result-size management.** Truncate + pre-summarize every AWS payload before it enters the
   model context. This protects the token budget and cost. Centralize in a `formatting.py` helper.
3. **Caching (optional).** Short-TTL Redis cache in front of `GetMetricData` — identical queries
   during an incident are common; cuts latency and AWS API cost.
4. **Observability of the observability tool (optional).** OpenTelemetry span per tool call.
5. **Actionable errors.** e.g. on `ResourceNotFound`, return "log group X not found; call
   `list_recent_alarms` to discover active resources" rather than a raw boto3 traceback.

---

## 8. Suggested repo structure

```
aws-observability-mcp/
├── README.md                     # public-facing; include the architecture diagram
├── requirements.txt              # PIN fastmcp + mcp + boto3 versions
├── Dockerfile
├── src/aws_observability_mcp/
│   ├── __init__.py
│   ├── server.py                 # FastMCP instance + tool registration
│   ├── auth.py                   # OAuth 2.1 config
│   ├── formatting.py             # truncation / summarization helpers
│   ├── cache.py                  # optional Redis TTL cache
│   ├── aws/
│   │   ├── cloudwatch.py         # GetMetricData, DescribeAlarms wrappers
│   │   ├── logs.py               # FilterLogEvents / Insights wrappers
│   │   └── ecs.py                # DescribeServices wrapper
│   └── tools/
│       ├── health.py
│       ├── metrics.py
│       ├── logs.py
│       ├── alarms.py
│       └── incident.py           # summarize_incident composite
├── tests/
│   ├── conftest.py               # moto @mock_aws fixtures + synthetic seeders
│   ├── test_metrics.py
│   ├── test_logs.py
│   ├── test_alarms.py
│   └── test_incident.py
├── evals/
│   └── evaluation.xml            # 10 realistic incident questions (see §11)
└── infra/
    └── deploy.md                 # scale-to-zero deploy notes
```

---

## 9. Testing strategy (no company AWS, near-zero cost)

**Tier 1 — `moto`, for all development + unit tests ($0).** Mocks AWS at the boto3 API level
with the unified `@mock_aws` decorator. Seed a synthetic incident, then call the tool and assert.

```python
import boto3
from moto import mock_aws

@mock_aws
def test_query_metrics_tool():
    cw = boto3.client("cloudwatch", region_name="us-east-1")
    cw.put_metric_data(
        Namespace="MyApp",
        MetricData=[{"MetricName": "5xxCount", "Value": 120, "Unit": "Count"}],
    )
    result = query_cloudwatch_metrics(namespace="MyApp", metric_name="5xxCount", ...)
    assert result.max == 120
```

`conftest.py` should provide reusable fixtures that seed a realistic "incident" (error-rate
spike + a firing alarm + matching error logs) so `summarize_incident` has something to correlate.

**Tier 2 — LocalStack, for one end-to-end demo ($0).** Run the AWS emulator in Docker; point
boto3 at `endpoint_url="http://localhost:4566"`. Use this to record the demo where Claude Desktop
or the MCP Inspector drives the live tools.

**Tier 3 — real AWS, only if you want a "real CloudWatch" screenshot (pennies).** This project
only *reads*, so it never spins up expensive compute. Push a few synthetic metrics with
`put_metric_data`, create 1–2 alarms, write some log events. CloudWatch has a free tier on top.

**Deployment proof (don't pay for always-on).** Deploy once to a scale-to-zero target (Lambda
container URL or Cloud Run), record the remote + OAuth flow, then tear it down. The artifacts that
matter are the `Dockerfile` + the recorded demo, not a 24/7 server.

---

## 10. Phased build plan (commit at each milestone)

- **Phase 0 — Scaffold.** Repo structure, `requirements.txt` (pinned), FastMCP instance, one
  trivial tool, run over **stdio**, verify in the **MCP Inspector**. ✅ first green path.
- **Phase 1 — AWS read tools on moto.** Implement `get_service_health`,
  `query_cloudwatch_metrics`, `tail_logs`, `list_recent_alarms` as thin `boto3` wrappers.
  Add truncation/summarization in `formatting.py`. Write `pytest` + `moto` tests for each.
- **Phase 2 — Composite tool.** Build `summarize_incident` (fan-out + correlation). Add a
  synthetic-incident fixture and a test proving the correlated digest.
- **Phase 3 — Remote + auth.** Swap stdio → **Streamable HTTP**, layer **OAuth 2.1 (PKCE)**,
  expose `/.well-known/oauth-protected-resource`. Add scoped tokens (RBAC scaffolding).
- **Phase 4 — Containerize + deploy.** `Dockerfile`, optional **OpenTelemetry** spans, deploy to
  a **scale-to-zero** target. Record the end-to-end demo (LocalStack or seeded real account).
- **Phase 5 — Evals + polish.** Write 10 evaluation questions (§11), polish the README with the
  architecture diagram, link the demo recording.

Realistic budget: Phases 0–2 are the bulk and are 100% free on moto. Phases 3–5 are the
production layer that differentiates the project.

---

## 11. Evaluations (MCP best practice)

Create `evals/evaluation.xml` with ~10 questions that each require **multiple read-only tool
calls** against a seeded dataset, with single verifiable answers. Example shape:

```xml
<evaluation>
  <qa_pair>
    <question>During the 14:00–14:30 UTC window, which service had a firing alarm AND a
    correlated 5xx error spike, and how many distinct error patterns appeared in its logs?</question>
    <answer>checkout-service, 3</answer>
  </qa_pair>
  <!-- 9 more -->
</evaluation>
```

---

## 12. AI / engineering topics this project demonstrates

- **MCP internals** — implementing tools, resources, prompts (not just consuming a server)
- **Tool / function calling** — how the model reads a schema, picks a tool, fills args, acts
- **Agent loop / ReAct** — reason → act → observe → repeat over your tools
- **Dynamic tool orchestration** — LLM composes a different sequence per question
- **Context-window & token management** — truncation/summarization before payloads hit the model
- **Prompt engineering** — tool descriptions/docstrings *are* prompts; plus the summarization prompt
- **Structured output / synthesis** — turning raw telemetry into a root-cause narrative
- *(Optional)* **LangGraph** — if you add a custom LangGraph agent that consumes the server via
  `langchain-mcp-adapters`

> Not covered (by design): transformer internals, embeddings, RAG/vector search, model training.
> Pair with the "Agentic RAG-over-MCP" project to add the RAG signal.

---

## 13. Reference material

**MCP / FastMCP**
- FastMCP docs: https://gofastmcp.com  (HTTP deployment + auth mounting patterns)
- FastMCP HTTP deployment: https://gofastmcp.com/deployment/http
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP spec sitemap: https://modelcontextprotocol.io/sitemap.xml  (fetch pages with `.md` suffix)

**AWS reference (study, don't copy)**
- `awslabs/mcp` CloudWatch MCP server (official, local-only): https://awslabs.github.io/mcp/servers/cloudwatch-mcp-server
- boto3 CloudWatch examples: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/get_metric_data.html

**Videos (watch in this order)**
- Microsoft "Python + MCP" series (server → deploy + OpenTelemetry → OAuth):
  https://techcommunity.microsoft.com/blog/azuredevcommunityblog/learn-how-to-build-mcp-servers-with-python-and-azure/4479402
  - Session 1 video: https://www.youtube.com/watch?v=_mUuhOwv9PY
- boto3 + CloudWatch in Python (the AWS tool guts): https://www.youtube.com/watch?v=nGlUakj7muk

**Testing**
- moto: https://github.com/getmoto/moto
- LocalStack: https://localstack.cloud

---

## 14. Suggested first prompts for Claude Code

1. "Read SPEC.md. Scaffold the repo per §8, set up `requirements.txt` with pinned `fastmcp`,
   `mcp`, and `boto3`, and create a minimal FastMCP server over stdio with one placeholder tool.
   Show me how to test it in the MCP Inspector." *(Phase 0)*
2. "Implement `query_cloudwatch_metrics` per §6.2 with a Pydantic input/output model, truncation
   in `formatting.py`, and a `pytest` + `moto` test that seeds a synthetic 5xx spike." *(Phase 1)*
3. "Implement the `summarize_incident` composite tool per §6.5 with a moto fixture that seeds a
   firing alarm + matching error logs, and a test asserting the correlated digest." *(Phase 2)*
