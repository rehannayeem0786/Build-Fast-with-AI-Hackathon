# NexusFlow AI ⚡
### Autonomous Multi-App Operations · Real MCP · Self-Healing Browser Agent · Fail-Safe HITL
**AI Build Challenge 2026 · Problem Statement 01: Autonomous Agents for Everyday Apps**

[![Benchmark Pass Rate](https://img.shields.io/badge/Benchmark--30-30%2F30%20Contract%20Passed-3fb950?style=for-the-badge&logo=pytest)](./eval/reports/BENCHMARK_REPORT.md)
[![Self-Healing Recovery](https://img.shields.io/badge/Self--Healing-3%2F3%20Recovered-38bdf8?style=for-the-badge)](./eval/reports/BENCHMARK_REPORT.md)
[![Suite Speedup](https://img.shields.io/badge/Speedup-6000x%2B%20(est.%20vs%20measured)-f2b632?style=for-the-badge)](./eval/reports/BENCHMARK_REPORT.md)
[![HITL Governance](https://img.shields.io/badge/SafeGuard-Fail--Safe%20HITL%20Gate-f85149?style=for-the-badge)](./app/core/guardrail.py)
[![MCP Transport](https://img.shields.io/badge/Transport-MCP%20stdio%20(official%20SDK)-a371f7?style=for-the-badge)](./app/mcp/server.py)
[![Browser Engine](https://img.shields.io/badge/Browser-Playwright%20Chromium-2ea44f?style=for-the-badge)](./app/agents/browser_agent.py)

---

## 📌 Executive Summary

**NexusFlow AI** is an autonomous operations agent that turns natural language goals into verified, cross-application workflows across SaaS backends (CRM, billing, spreadsheets) and web applications — and it runs on **real infrastructure, not simulations of one**:

- **Real MCP:** an official-SDK MCP server (12 tools) spawned as a subprocess over **stdio**, driven by a genuine MCP client (initialize handshake → `tools/list` → `tools/call`).
- **Real browser:** a headless **Chromium (Playwright)** engine that fills forms, clicks buttons, scrapes live DOM, and self-heals through a **5-stage grounding cascade** — including accessibility-tree grounding and a persisted *learned-selector memory*.
- **Real planning:** an optional LLM planner (OpenAI / Anthropic, structured JSON over full tool schemas) with a deterministic intent-composition fallback that plans **any** goal — never a canned script.
- **Real safety:** a SafeGuard HITL gate with a 4-tier risk matrix, before/after JSON diffs, APPROVE / **MODIFY** / REJECT decisions, and a **fail-safe timeout that deny-defaults to REJECT** so a demo can never hang.
- **Real accountability:** every run emits a JSON trace; mutations record **compensating actions** so any workflow can be **rolled back** with one API call.

---

## 🏛️ System Architecture

```
                                  [ User Goal / Prompt ]
                                             │
                                             ▼
                                  ┌─────────────────────┐
                                  │  Goal-to-DAG        │
                                  │  Planner            │
                                  │  • LLM (optional)   │
                                  │  • Heuristic engine │
                                  └──────────┬──────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
          ┌───────────────────────────┐               ┌───────────────────────────┐
          │   SafeGuard Risk Gate     │               │   Telemetry & Traces      │
          │   • LOW: Auto-Execute     │               │   • JSON audit trails     │
          │   • HIGH: Audit-Logged    │               │   • Self-healing RCA      │
          │   • CRITICAL: HITL Diff   │               │   • HITL decision log     │
          │   • Fail-safe timeout     │               │   • Undo/compensation log │
          └────────────┬──────────────┘               └───────────────────────────┘
                       │
       ┌───────────────┴────────────────────────┐
       ▼                                        ▼
┌─────────────────────────────┐   ┌─────────────────────────────────┐
│   MCP Server (stdio)        │   │   Self-Healing Browser Agent    │
│   official `mcp` SDK        │   │   Stage 0: Learned Memory       │
│   • CRM (12 tools)          │   │   Stage 1: Exact CSS/ID         │
│   • Billing                 │   │   Stage 2: Semantic Text        │
│   • Sheets (+ undo)         │   │   Stage 3: Accessibility Tree   │
│   • Outbound email          │   │   Stage 4: Form Proximity       │
└─────────────────────────────┘   └─────────────────────────────────┘
```


---

## 🏆 The Five Mandatory Hackathon Proofs

### 1. Baseline vs Result Comparison

> Baseline figures are **estimates** for a person doing the same 30 tasks by hand;
> NexusFlow figures are **measured wall-clock** from `python run_eval.py`.

| Operational Metric | Estimated Manual Baseline | NexusFlow AI (Measured) | Improvement |
| :--- | :--- | :--- | :--- |
| **Total time for the 30-task suite** | ~43,000s (~11.9 h) | ~7s (avg ~0.24s/task) | **~6,000x suite speedup** |
| **Tasks passing strict contract checks** | 30 (by hand, unverified) | **30/30** (tools + status + gates + postconditions) | graded, not asserted |
| **Selector breakage recovery** | manual re-inspection each time | **3/3 recovered** via 5-stage cascade | self-healing |
| **High-risk actions gated** | depends on operator discipline | **7 gates fired, 0 unauthorized** | deny-by-default |
| **LLM cost per run** | — | **$0.00** (deterministic planner; LLM optional) | transparent accounting |

### 2. Verifiable Benchmark-30 Results
Run `python run_eval.py` and every task is graded against a **declared contract** — expected tools planned *and* executed, expected final status, real gate decisions, and side-effect postconditions **re-verified through the MCP transport**:

- **Pass Rate:** `30/30` (100%) contract-checked
- **Self-Healing Recovery:** `3/3` mutated-DOM tasks recovered (semantic → accessibility-tree → learned-memory paths)
- **SafeGuard Gates Exercised:** `7` tasks paused for scripted **APPROVE / REJECT / MODIFY** decisions — never bypassed with auto-approve
- **Engines actually used:** `MCP=mcp_stdio` · `browser=PLAYWRIGHT` (reported by the run itself)
- **Honest cost:** `$0.00` when the deterministic planner runs; token cost only when LLM keys are configured

*Full matrix and per-task notes: [`eval/reports/BENCHMARK_REPORT.md`](./eval/reports/BENCHMARK_REPORT.md).*

### 3. SafeGuard Human-in-the-Loop (HITL) Gate
Every proposed action is classified on a 4-tier risk matrix:
1. `LOW` (Read-only / scrape / query) ➔ **Fully Autonomous Execution**
2. `MEDIUM` (Draft generation / cache updates) ➔ **Autonomous with Audit Logging**
3. `HIGH` (Database records / sheet updates) ➔ **Staged Diff Preview + compensating-action logging**
4. `CRITICAL` (Financial charges / outbound emails / deletions) ➔ **MANDATORY Human Approval Modal**

At a CRITICAL step the state machine pauses, computes a **Before vs After JSON diff**, and streams an authorization card to the UI. The human can:
- **APPROVE** — execute as proposed
- **MODIFY** — edit parameters (e.g. amount, subject) which are applied before execution
- **REJECT** — abort the workflow with zero side effects

**Fail-safe:** if no decision arrives within `APPROVAL_TIMEOUT_SEC` (default 120s), the action is **auto-REJECTED** — deny-by-default, so an unattended demo can never hang or leak an unauthorized action.

### 4. Verifiable Traces, Self-Healing RCA & Undo
Every run writes `eval/reports/trace_<workflow_id>_<ts>.json` documenting:
- Millisecond timestamps per step, tool inputs/outputs, status (`SUCCESS` / `RECOVERED` / `FAILED` / rejected)
- Self-healing RCA: the failed selector, which stage recovered it, the resolved element
- Full HITL decision log (decision, diffs) — the proof that gates actually fired
- Planner mode (`LLM` / `HEURISTIC`) and MCP transport used

Reversible mutations (sheet appends, CRM updates) additionally record **compensating actions** — roll a whole workflow back with:

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/<workflow_id>/undo
```

### 5. Context Note
- **Target Persona:** Operations Managers, RevOps Specialists, Financial Clerks, and Growth Engineers managing multi-app operational stacks.
- **Data Provenance:** Synthetic enterprise sandbox schemas modeled after production HubSpot CRM, Stripe Invoicing, and Google Sheets formats — zero privacy leaks, 100% offline reproducibility.
- **Scope:** End-to-end autonomous multi-app DAG planning, Model Context Protocol integration, real-browser DOM self-healing, human-in-the-loop safety governance, and rollback.


---

## 🔬 Verification Stack (three layers)

| Layer | Command | What it proves |
| :--- | :--- | :--- |
| **Unit + integration tests (17)** | `python -m pytest tests/` | planner topology, MCP stdio roundtrip, real Chromium healing, HITL reject/timeout/modify, rollback, API endpoints |
| **Benchmark-30 (contract-graded)** | `python run_eval.py` | end-to-end workflows: tools, statuses, gate decisions, MCP-verified postconditions |
| **Live dashboard** | `python app/main.py` | human-visible demo: WebSocket traces, HITL modal, DOM mutation sandbox |

---

## 🚀 Quickstart & Setup Guide

### 1. Environment Setup
```bash
# Clone the repository
cd buildfastwithai

# Create virtual environment
python -m venv .venv
source .venv/Scripts/activate   # On Windows (or source .venv/bin/activate on Linux/Mac)

# Install dependencies (includes the official MCP SDK)
pip install -r requirements.txt

# Install the Chromium browser used by the self-healing agent
playwright install chromium
```

### 2. Run Test Suite
```bash
python -m pytest tests/
```

### 3. Run Benchmark-30 Evaluation
```bash
python run_eval.py
```
Writes `eval/reports/BENCHMARK_REPORT.md`, `benchmark_30_summary.json`, and per-run JSON traces.

### 4. Launch Interactive Web Dashboard & Sandbox
```bash
python app/main.py
```
Open `http://127.0.0.1:8000` — enter any goal, watch the DAG execute live, flip the portal to **Mutated DOM (v2)** to trigger self-healing, approve/modify/reject HITL diffs, and inspect traces.

### 5. (Optional) Enable the LLM Planner
```bash
cp .env.example .env
# set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env
```
Without keys the deterministic planner is used (zero cost); with keys, goals are decomposed by the LLM over the full MCP tool schemas — with hallucinated tools rejected back to the heuristic.

### Standalone MCP Server (for Claude Desktop, Cursor, etc.)
```bash
python -m app.mcp.server              # stdio transport
python -m app.mcp.server --http 8765  # streamable HTTP
```

---

## 🤖 AI Tool & Model Disclosure
- **Planning:** LLM planner via official REST APIs (gpt-4o / Anthropic models, structured JSON, tool-schema validation) — *optional*; deterministic intent-composition engine is the default fallback and is what the benchmark runs use.
- **Tool standard:** Model Context Protocol (MCP) via the **official `mcp` Python SDK** — real stdio server + client handshake.
- **Browser automation:** Playwright (headless Chromium) with accessibility-tree (`aria_snapshot`) grounding; BeautifulSoup4 only as a last-resort offline fallback (and the engine actually used is always reported).
- **Backend & telemetry:** FastAPI, WebSockets, Pydantic v2, pytest + pytest-asyncio.

## 👥 Team Nexus
- **Lead AI Systems Architect:** DAG planning, self-healing browser engine, SafeGuard engine
- **Full-Stack & MCP Engineer:** FastAPI server, WebSocket telemetry, web UI dashboard
- **Evaluation & QA Lead:** Benchmark-30 suite, failure RCA, governance compliance tests
