# Project design (use cases, architecture, tools, data sources)

This is a personal portfolio project — an agentic AI HR helpdesk — not built for
any specific employer. Scope is deliberately limited to HR queries only (no IT/
warehouse-safety, which were part of an earlier draft of this project and have
since been dropped — see note below).

The full list of use cases lives in `docs/use_cases.md` — that file is the
single source of truth; it is not duplicated here to avoid the two documents
drifting out of sync.

## Workflow (same pattern across use cases)

`Employee asks → agent identifies them (auth) → retrieves relevant policy (RAG) and/or looks up their record → answers, fills a template, or calls a tool (ticket/approval) → escalates to a human if sensitive`

This tells us exactly what's needed: **RAG docs** (real policy content) +
**auth** (who's asking) + **mock employee data** (private records no public
source could ethically provide) + **templates** (standard HR document formats)
+ **a ticketing/approval mechanism** for anything with a real-world consequence.

## Real data sources

| Use case(s) | Real source | Why it fits |
|---|---|---|
| Sick/absence, grievance, flexible working | **ACAS** (acas.org.uk) — UK's official employment relations body | Real, free, UK-wide, exactly the policy areas asked about |
| Workplace pension | **NEST Pension** (nestpensions.org.uk) | Real UK government-backed auto-enrolment scheme; public member help centre |
| Mileage/expenses | **HMRC / GOV.UK Content API** — Approved Mileage Allowance Payments (AMAP) rates | Real, official, current UK rates, fetched via the structured GOV.UK Content API rather than scraped |

## Mock data sources

| Source | What it provides | Provenance |
|---|---|---|
| `data/mock_hr/employees/employee_records.csv` | Employee identity, job, pay, leave balance fields used across most use cases | Synthetic HR dataset — not self-generated. Sourced from [synthetic-hris.com](https://synthetic-hris.com/), a synthetic HRIS data generator. Records represent fictional individuals; no real personal data is used. |
| `data/mock_hr/templates/*.txt` (+ `_manifest.json`) | 10 standard HR document templates (verification letter, P45/P60 request, change of details, flexible working request, etc.) | Authored for this project — real-world document *formats*, fictional company content |

> **Note on removed scope:** an earlier draft of this project targeted a
> specific builders'-merchant use case, including warehouse safety (HSE
> guidance) and IT password reset (Microsoft 365 docs + Microsoft Entra ID
> auth). Both were dropped when the project scope was narrowed to
> HR-only. If IT/auth is reintroduced later, the original reasoning for
> pairing Microsoft 365 docs with Entra ID (same-vendor consistency) is
> preserved in earlier project notes, but a lighter-weight mock auth
> mechanism is likely sufficient for the current HR-only scope and should
> be decided explicitly rather than inherited from the dropped IT plan.

## Real tools (integration layer)

| Tool | Real service | Why chosen |
|---|---|---|
| Ticketing / approval workflow (leave requests, P45/P60, personal detail changes, flexible working) | **Zammad** (self-hosted, open-source, AGPLv3) | Genuinely free, open-source, full REST API from day one — unlike Freshdesk's free tier, which blocks API access |
| Employee lookup / leave balance / template data | Mock CSV + scoped MCP tools | No public source can ethically provide private employee records; access is field-scoped per tool (least-privilege), not a raw database query |

## Why this combination is coherent

- **All three real sources (ACAS, NEST, HMRC) are UK regulatory/public-sector bodies** — consistent domain, so the RAG corpus reads as one coherent knowledge base rather than a grab-bag of unrelated sites.
- **Mocks are limited to genuinely private data and authored document templates** — never standing in for content that a real public source could have provided instead.
- **Every mock/synthetic input has a stated, honest provenance** (either "sourced from synthetic-hris.com" or "authored for this project") — nothing is presented as more real than it is.

This gives a defensible project story: *"I integrated real UK regulatory data sources (ACAS, NEST, HMRC via its structured Content API) with an open-source ticketing/approval tool (Zammad), and used clearly-sourced synthetic HR data only where no real source could ethically exist."*

---
# Development Plan
Here's the full plan, structured the way a senior engineer would actually sequence it — data and tools before orchestration, orchestration before guardrails, guardrails before deployment.

## Phase 1 — Foundation

**1. Scope & define success criteria**
Nail down the 10 use cases, what "correct" looks like for each, and what's explicitly out of scope (e.g. no autonomous pay changes). Write this down before any code — it becomes your evaluation rubric later.
*Tools: just a doc (Notion/markdown).*

**2. Collect & prepare data sources**
Gather the real public docs (ACAS, HSE, NEST, HMRC, Microsoft 365 support pages), clean them (strip nav/boilerplate), chunk them sensibly.
*Tools: `requests`/`BeautifulSoup` or a scraping library, `unstructured` or `langchain` document loaders.*

## Phase 2 — Core RAG

**3. Build the ingestion & embedding pipeline**
Chunk → embed → store in a vector DB. This is a one-time (or scheduled) pipeline, separate from the live agent.
*Tools: OpenAI/Cohere embeddings or open-source (BGE), Chroma or Qdrant (both have free local/self-hosted options).*

**4. Build & evaluate the retriever**
Test retrieval quality in isolation before wiring it to an LLM — this is the step juniors skip and pay for later.
*Tools: RAGAS (retrieval-specific metrics: faithfulness, context relevance).*

## Phase 3 — Tools & Agent

**5. Build tools as MCP servers**
Wrap each real integration (Zammad ticketing, Entra ID auth, mock HR DB) as a standalone MCP server with a clean schema — not hardcoded into the agent.
*Tools: MCP Python/TypeScript SDK, FastAPI (if wrapping mock DBs as APIs first).*

**6. Build the agent orchestrator**
Wire the LLM + retriever + MCP tools into a reasoning loop (ReAct-style) with defined state.
*Tools: LangGraph (industry standard for this), Claude/GPT API.*

**7. Add memory/state management**
Short-term conversation memory so multi-turn edits ("make that ticket high priority") work.
*Tools: LangGraph's built-in checkpointing, or Redis if you want it decoupled.*

## Phase 4 — Safety Layer

**8. Add input & output guardrails**
Injection detection on input; hallucination/policy/confidence checks on output before anything reaches the user.
*Tools: Guardrails AI or NeMo Guardrails, or a lightweight custom LLM-as-judge check.*

**9. Add human-in-the-loop escalation**
Explicit trigger conditions (low confidence, sensitive topic, action with consequences) that pause the agent and route to a human queue.
*Tools: can be a simple flag + ticket creation via the same MCP ticketing tool.*

## Phase 5 — Testing & Evaluation

**10. Build an offline evaluation suite**
A fixed set of test questions (your 10 use cases + edge cases) run automatically against the agent, scored for correctness/faithfulness — this is what "gold standard" agentic AI teams do before every deploy, not just manual spot-checks.
*Tools: RAGAS, promptfoo, or a custom eval harness; Langfuse/LangSmith for trace-based review.*

## Phase 6 — Deployment

**11. Containerize the application**
Package the agent service (and any mock APIs) into Docker images.
*Tools: Docker.*

**12. Deploy to the cloud**
Stand up the agent API, vector DB, and MCP servers as running services.
*Tools: AWS (ECS/Fargate or a simple EC2 + Docker Compose) or Azure (since Entra ID is Azure-native) — pick one to keep the identity/infra story coherent.*

**13. Set up CI/CD**
Automated tests (including the eval suite from step 10) run on every change before deploy.
*Tools: GitHub Actions.*

## Phase 7 — Production Operations

**14. Add observability & monitoring**
Full tracing of every LLM call, tool call, and guardrail decision in production — not just uptime monitoring.
*Tools: Langfuse (self-hostable, free) or LangSmith.*

**15. Set up cost & usage tracking**
Token usage, per-request cost, and rate limits — a production concern that's invisible in a demo but critical in real deployment.
*Tools: Langfuse cost tracking, or simple custom logging + a dashboard.*