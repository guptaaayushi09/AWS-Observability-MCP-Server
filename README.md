# AWS Observability MCP Server

A remote, OAuth-secured [MCP](https://modelcontextprotocol.io) server that exposes an AWS
CloudWatch + ECS observability stack to any LLM agent, enabling natural-language incident
investigation.

> "Why is the checkout service throwing 5xxs in the last 15 minutes?"
>
> The agent autonomously calls `query_cloudwatch_metrics` → `tail_logs` → `list_recent_alarms`,
> correlates the results, and returns a root-cause summary.

## What it is

A server that wraps an AWS monitoring stack (CloudWatch metrics, CloudWatch Logs, alarms, ECS
service health) into a small set of **typed MCP tools** that any LLM agent — Claude Desktop, a
custom LangGraph agent, the MCP Inspector — can call over a standard protocol, without ever
touching `boto3` or AWS credentials directly.

## Differentiation

AWS ships an open-source local CloudWatch MCP server (`awslabs/mcp`). This project **productionizes
a local observability MCP server into a secure, remote, multi-tenant service**: Streamable HTTP
transport, OAuth 2.1 auth, tool-level RBAC, result truncation for context budget, and a
scale-to-zero deployment.

## Project layout

```
aws-observability-mcp/
├── src/aws_observability_mcp/
│   ├── aws/            # boto3 client wrappers
│   └── tools/          # typed MCP tool definitions
├── tests/              # pytest + moto (mocks AWS at the boto3 API level)
├── evals/              # agent-level evaluations
├── infra/              # deployment (scale-to-zero)
└── requirements.txt
```

See [`aws-observability-mcp-server-SPEC.md`](./aws-observability-mcp-server-SPEC.md) for the full
design, tool specs, testing strategy, and phased build plan.

## Development

```bash
cd aws-observability-mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```
