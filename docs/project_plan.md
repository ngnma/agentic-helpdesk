# Proposal of the project design (use cases, architucture, tools and datasources)
## Top 10 use cases (as PM, thinking about  actual workforce)

The company has ~90 staff across 5 branches: warehouse/yard staff, branch counter/sales staff, drivers, and office admin. That workforce profile drives the real questions:

1. Annual leave balance & how to request it
2. Sick/absence reporting process
3. **Manual handling / PPE / forklift (FLT) safety procedures** — critical for a builders' merchant warehouse
4. Mileage claims for inter-branch travel/deliveries
5. Payslip / pay date queries
6. IT password reset / access request for internal systems
7. Workplace pension (auto-enrolment) questions
8. Forklift licence / first aid certificate renewal reminders
9. Who do I raise a grievance/complaint with
10. Bank holiday & overtime pay policy

## Workflow (same pattern for all 10)

`Employee asks → agent identifies them (auth) → retrieves relevant policy (RAG) → answers, or calls a tool (ticket/lookup) → escalates to human if sensitive`

This tells us exactly what's needed: **RAG docs** (policy content) + **auth** (who's asking) + **ticketing** (action/escalation) + **mock private data** (things no public source can ethically provide).

## Real data sources

| Use case | Real source | Why it fits | Free? |
|---|---|---|---|
| Leave, sick pay, grievance, parental leave | **ACAS** (acas.org.uk) — UK's official employment relations body | Real, free, UK-wide (covers Scotland), exactly the policy areas asked about | Free, public |
| Manual handling, PPE, forklift/workplace transport | **HSE** (hse.gov.uk) — Health and Safety Executive | Genuinely core to a builders' merchant warehouse — HSE publishes detailed free guides on exactly this ("Warehousing and storage," "Workplace transport safety") | Free, public |
| Workplace pension | **NEST Pension** (nestpension.org.uk) | NEST is the real UK government-backed auto-enrolment scheme most SMEs use; has public employee FAQs | Free, public |
| Mileage/expenses | **HMRC** — Approved Mileage Allowance Payments (AMAP) rates page | Real, official, current UK rates — no invented numbers | Free, public |
| IT password reset / access requests | **Microsoft 365 official support docs** | UK SMEs of this size overwhelmingly run Microsoft 365, not Google Workspace — this keeps the KB coherent with the auth choice below | Free, public |

## Real tools (integration layer)

| Tool | Real service | Why chosen over the obvious alternative |
|---|---|---|
| Ticketing (create/update/query tickets) | **Zammad** (self-hosted, open-source, AGPLv3) | Freshdesk's free plan **blocks API access** (verified) — useless for a tool-calling demo. Zammad is genuinely free, open-source, and has a full REST API from day one. |
| Employee auth/directory (identify who's asking) | **Microsoft Entra ID (Free tier)** | Permanently free, real OAuth/SSO, and matches the Microsoft 365 IT docs above — a consistent Microsoft-based stack rather than mixing ecosystems |
| Leave balance lookup | Mock DB | No public API exposes real employees' personal leave balances — inherently private company data |
| Forklift/training cert tracker | Mock DB | Private HR record — no ethical real source exists |

## Why this combination is coherent (your consistency concern)

- **IT docs (Microsoft 365) ↔ Auth (Entra ID)** — same vendor ecosystem, so "reset your password" instructions actually match how the demo authenticates users.
- **HR/pension/expense docs are all UK-government-adjacent bodies** (ACAS, NEST, HMRC) — consistent regulatory domain.
- **HSE content is the one that makes this recognizably a builders'-merchant/warehouse project**, not a generic office helpdesk — this is your strongest differentiator in an interview.
- **Mocks are limited to genuinely private data only**, which — as discussed earlier — reads as good judgement rather than a shortcut.

This gives you a defensible story: *"I integrated real UK regulatory/public-sector data sources (ACAS, HSE, NEST, HMRC) with a real open-source ticketing system (Zammad) and Microsoft Entra ID auth, mocking only genuinely private company records."*

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