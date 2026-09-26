# NexusFlow AI · Benchmark-30 Evaluation Report

**Evaluation Date:** 2026-09-26 13:41:24 IST  
**Total Test Workflows:** 30  
**Overall Pass Rate:** `100.0%` (30/30 — each task graded against its own contract: expected tools, status, gate decisions, postconditions)  
**Self-Healing Recovery Rate:** `100.0%` (3/3 mutated-DOM tasks recovered)  
**SafeGuard Gates Exercised:** `7` tasks paused for a real scripted human decision (APPROVE / REJECT / MODIFY)  
**Measured Agent Wall-Clock (all 30 tasks):** `6.104s` (avg 0.203s per task)  
**Estimated Manual Baseline (all 30 tasks):** `43000s` (~11.9 h)  
**Suite Speedup (est. manual total / measured agent total):** `7044.6x`  
**Total Planning Cost:** $0.00 (deterministic planner — no LLM inference)  
**Engines:** planner=HEURISTIC · MCP=MCP_STDIO · browser=PLAYWRIGHT  

---

## 1. Baseline vs Result Comparison

> Manual baseline figures are **estimates** for a person performing the same
> 30 tasks through UIs; agent figures are **measured wall-clock** from this run.

| Metric | Estimated Manual Baseline | NexusFlow AI (Measured) | Delta |
| :--- | :--- | :--- | :--- |
| **Total task time** | 43000s (~11.9 h) | 6.104s | **7044.6x faster (avg/task)** |
| **Tasks completed end-to-end** | 30 (by hand) | 30/30 pass strict contract checks | graded, not asserted |
| **DOM breakage recovery** | manual re-inspection each time | 3/3 recovered via 5-stage cascade | self-healing |
| **High-risk actions gated** | depends on operator discipline | 7 gates fired, 0 executed unauthorized | deny-by-default |
| **LLM cost / run** | — | $0.00 (deterministic planner — no LLM inference) | transparent accounting |

---

## 2. Benchmark-30 Task Matrix

| ID | Category | Task | Status | Agent Time | Baseline (est.) | Speedup | Self-Healing | SafeGuard | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| BENCH-01 | CRM Operations | High-Value Lead Pipeline Qualification | ✅ PASS | 5ms | 1800s | 367346.9x | — | — | — |
| BENCH-02 | CRM Operations | Enterprise Deal Auto-Creation | ✅ PASS | 2ms | 1200s | 600000.0x | — | — | — |
| BENCH-03 | CRM Operations | Stale Lead Re-engagement Filter | ✅ PASS | 29ms | 1500s | 51369.9x | — | 🛡️ Gated | — |
| BENCH-04 | CRM Operations | Rep Territory Reassignment | ✅ PASS | 18ms | 900s | 49723.8x | — | — | — |
| BENCH-05 | CRM Operations | Lead Score Calibration Batch | ✅ PASS | 16ms | 2100s | 132911.4x | — | — | — |
| BENCH-06 | CRM Operations | Pipeline Stage Reconciliation | ✅ PASS | 16ms | 1600s | 101910.8x | — | — | — |
| BENCH-07 | Billing Operations | Overdue Invoices Audit & Reconcile | ✅ PASS | 780ms | 2400s | 3077.7x | — | — | — |
| BENCH-08 | Billing Operations | Automated Overdue Payment Notice | ✅ PASS | 26ms | 1200s | 46153.8x | — | 🛡️ Gated | — |
| BENCH-09 | Billing Operations | Recurring Subscription Audit | ✅ PASS | 8ms | 1800s | 225000.0x | — | — | — |
| BENCH-10 | Billing Operations | Failed Payment Charge Recovery | ✅ PASS | 9ms | 1500s | 161290.3x | — | — | — |
| BENCH-11 | Billing Operations | Tier-Upgrade Revenue Recompute | ✅ PASS | 6ms | 2000s | 327868.9x | — | — | — |
| BENCH-12 | Billing Operations | Executive Billing Delinquency Summary | ✅ PASS | 6ms | 1800s | 310344.8x | — | — | — |
| BENCH-13 | Web Automation & Grounding | Standard Portal Table Scrape | ✅ PASS | 803ms | 900s | 1121.4x | — | — | — |
| BENCH-14 | Web Automation & Grounding | Web Form Submit (Standard DOM v1) | ✅ PASS | 863ms | 600s | 695.3x | — | — | — |
| BENCH-15 | Web Automation & Grounding | Self-Healing Form Submit (Mutated DOM v2) | ✅ PASS | 892ms | 900s | 1009.4x | 🔄 Recovered | — | — |
| BENCH-16 | Web Automation & Grounding | Self-Healing Dynamic Layout Shift Recovery | ✅ PASS | 790ms | 1100s | 1391.9x | 🔄 Recovered | — | — |
| BENCH-17 | Web Automation & Grounding | Multi-Step Scrape & CRM Lead Enrichment | ✅ PASS | 753ms | 1800s | 2390.8x | — | — | — |
| BENCH-18 | Web Automation & Grounding | Self-Healing Complex Partner Intake | ✅ PASS | 873ms | 1400s | 1602.9x | 🔄 Recovered | — | — |
| BENCH-19 | Tabular Operations | Executive Ops Sheet Sync | ✅ PASS | 6ms | 900s | 157894.7x | — | — | — |
| BENCH-20 | Tabular Operations | Cross-App Health Status Reconcile | ✅ PASS | 0ms | 1800s | 18000000.0x | — | — | — |
| BENCH-21 | Tabular Operations | Audit Trail Logging | ✅ PASS | 4ms | 1200s | 279069.8x | — | — | — |
| BENCH-22 | Tabular Operations | Multi-Region ARR Aggregation | ✅ PASS | 0ms | 1500s | 15000000.0x | — | — | — |
| BENCH-23 | Tabular Operations | Data Cleansing & Normalization | ✅ PASS | 25ms | 2400s | 94861.7x | — | 🛡️ Gated | — |
| BENCH-24 | Tabular Operations | Weekly Pipeline Velocity Snapshot | ✅ PASS | 16ms | 2100s | 133758.0x | — | — | — |
| BENCH-25 | Governance & Safety | Critical Financial Charge Gate | ✅ PASS | 32ms | 1200s | 37854.9x | — | 🛡️ Gated | — |
| BENCH-26 | Governance & Safety | External Client Email Dispatch Gate | ✅ PASS | 32ms | 900s | 28213.2x | — | 🛡️ Gated | — |
| BENCH-27 | Governance & Safety | Human Approval Rejection Flow | ✅ PASS | 32ms | 600s | 18750.0x | — | 🛡️ Gated | — |
| BENCH-28 | Governance & Safety | Human-Modified Parameter Flow | ✅ PASS | 47ms | 900s | 18987.3x | — | 🛡️ Gated | — |
| BENCH-29 | Governance & Safety | Low-Risk Autonomous Bypass Verification | ✅ PASS | 16ms | 600s | 37267.1x | — | — | — |
| BENCH-30 | Governance & Safety | End-to-End Governance Audit Verification | ✅ PASS | 0ms | 2400s | 24000000.0x | — | — | — |

---

## 3. Verification Methodology

- **Contract grading:** every task declares required tools, expected final status,
  and gate behavior — a run only passes if the contract holds (not merely 'no crash').
- **Real gate decisions:** APPROVE / REJECT / MODIFY are submitted through the same
  API a human uses in the UI; gates are never bypassed with auto-approve.
- **Side effects verified through MCP:** charge postconditions re-query the billing
  server over the MCP transport after execution.
- **Timings are measured** (no floors or synthetic zeros); baseline column is an
  estimate and labeled as such.

## 4. Mandatory Proof 5: Context Note
**Target Persona:** Operations Managers, RevOps Specialists, and Growth Clerks executing daily 15-50 step workflows across disconnected web applications, CRMs, and spreadsheets.
**Data Provenance:** Synthetic enterprise schemas modeled after production HubSpot, Stripe Billing, and Google Sheets structures to ensure zero privacy leaks and 100% reproducible evaluation.
**Coverage:** End-to-end autonomous multi-app DAG planning, Model Context Protocol tool execution, live DOM self-healing, and human-in-the-loop governance diffs.