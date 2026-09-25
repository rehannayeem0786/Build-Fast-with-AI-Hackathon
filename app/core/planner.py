import json
import re
import time
import uuid
from typing import Dict, List, Any, Optional

from app.core.models import WorkflowDAG, WorkflowStep, ToolType, RiskLevel
from app.core.guardrail import safeguard
from app.config import settings

# LLM system prompt asking for a dependency-aware DAG in strict JSON.
PLANNER_SYSTEM_PROMPT = """You are an enterprise operations workflow planner.
Given a user goal and a list of available MCP tools (with JSON schemas), produce a
dependency-aware execution plan as STRICT JSON with this exact shape:
{"steps": [{"id": "step-1", "name": str, "description": str,
  "tool_name": str, "parameters": object, "dependencies": [str, ...]}]}
Rules:
- Only use tools from the provided list (browser tools allowed: scrape_table, fill_form_and_click).
- ids must be step-1, step-2, ... in execution order.
- dependencies reference earlier step ids only; use [] for the first step.
- Read-only steps first, mutations after, irreversible actions (email/charge) last.
- Output JSON only. No prose, no markdown fences."""


class GoalToDAGPlanner:
    """
    Hierarchical DAG Planner.

    Two planning modes:
      1. LLM PLANNER  â€” when OPENAI_API_KEY / ANTHROPIC_API_KEY is configured,
         the goal is decomposed by an LLM with full tool schemas (structured JSON
         output, validated, risk-assessed).
      2. HEURISTIC PLANNER â€” deterministic intent-composition engine used as
         fallback (and by default in offline/demo runs). Detects operational
         intents in the goal and composes a dependency-aware plan from them,
         instead of matching a fixed set of canned scenarios.
    """

    def __init__(self):
        self.last_mode: str = "HEURISTIC"
        self.last_model: Optional[str] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def plan_workflow(self, goal: str) -> WorkflowDAG:
        steps: Optional[List[WorkflowStep]] = None
        self.last_mode, self.last_model = "HEURISTIC", None

        if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY:
            try:
                steps = self._plan_with_llm(goal)
                if steps:
                    self.last_mode = "LLM"
                    self.last_model = settings.DEFAULT_PLANNER_MODEL
            except Exception:
                steps = None  # fall back to heuristic planner

        if steps is None:
            steps = self._plan_heuristic(goal)

        # Ensure risk assessment and approval flags are calibrated
        for s in steps:
            risk, req_app = safeguard.assess_risk(s.tool_name, s.parameters)
            s.risk_level = risk
            s.requires_human_approval = req_app

        dag = WorkflowDAG(
            workflow_id=f"wf-{uuid.uuid4().hex[:8]}",
            goal=goal,
            created_at=time.time(),
            steps=steps,
            total_steps=len(steps),
            completed_steps=0,
            overall_status="PLANNED",
            # Honest accounting: heuristic planning consumes zero LLM tokens.
            estimated_cost_usd=(round(0.04 * len(steps) + 0.05, 4)
                                if self.last_mode == "LLM" else 0.0),
            planner_mode=self.last_mode,
            planner_model=self.last_model,
        )
        return dag

    # ------------------------------------------------------------------
    # Mode 1: LLM planner (structured tool-calling)
    # ------------------------------------------------------------------
    def _plan_with_llm(self, goal: str) -> Optional[List[WorkflowStep]]:
        from app.agents.mcp_hub import mcp_hub
        tools_payload = [
            {"name": t["name"], "description": t["description"],
             "parameters": t["parameters"]}
            for t in mcp_hub.list_mcp_tools()
        ]
        user_prompt = (
            f"GOAL: {goal}\n\n"
            f"AVAILABLE TOOLS (JSON schemas):\n{json.dumps(tools_payload, indent=2)}"
        )

        raw = self._call_llm(user_prompt)
        if not raw:
            return None
        data = self._parse_json_loosely(raw)
        if not data or "steps" not in data:
            return None

        steps: List[WorkflowStep] = []
        seen_ids = set()
        for i, s in enumerate(data["steps"]):
            step_id = s.get("id") or f"step-{i + 1}"
            tool_name = s.get("tool_name", "")
            # Reject hallucinated tools — fall back to heuristic planner
            if tool_name not in mcp_hub.tools and tool_name not in (
                    "scrape_table", "fill_form_and_click"):
                return None
            deps = [d for d in (s.get("dependencies") or []) if d in seen_ids]
            steps.append(WorkflowStep(
                id=step_id,
                name=str(s.get("name", f"Step {i + 1}"))[:120],
                description=str(s.get("description", ""))[:500],
                tool_type=(ToolType.BROWSER if tool_name in
                           ("scrape_table", "fill_form_and_click") else ToolType.MCP_TOOL),
                tool_name=tool_name,
                parameters=s.get("parameters") or {},
                dependencies=deps,
            ))
            seen_ids.add(step_id)

        return steps or None

    def _call_llm(self, user_prompt: str) -> Optional[str]:
        """Call OpenAI or Anthropic (whichever key is present). Returns raw text."""
        import httpx
        timeout = 25.0

        if settings.OPENAI_API_KEY:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.DEFAULT_PLANNER_MODEL,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        if settings.ANTHROPIC_API_KEY:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01"},
                json={
                    "model": settings.DEFAULT_PLANNER_MODEL,
                    "max_tokens": 2000,
                    "system": PLANNER_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

        return None

    @staticmethod
    def _parse_json_loosely(text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON even when wrapped in ``` fences or prose."""
        text = text.strip()
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

        return dag


    # ------------------------------------------------------------------
    # Mode 2: Heuristic intent-composition planner (deterministic fallback)
    # ------------------------------------------------------------------
    @staticmethod
    def _extract(pattern: str, text: str, default: Any = None, cast=lambda x: x) -> Any:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return cast(m.group(1))
            except Exception:
                return default
        return default

    def _detect_intents(self, g: str) -> Dict[str, bool]:
        """Classify operational intents present in the (lowercased) goal."""
        has_update_word = "update" in g and any(k in g for k in ("crm", "lead", "record"))
        return {
            "leads": any(k in g for k in ("lead", "crm", "prospect", "pipeline", "deal", "qualif")),
            "invoices": any(k in g for k in ("invoice", "billing", "overdue", "payment",
                                             "reconcil", "subscription", "dunning")),
            "sheet_read": ("sheet" in g or "spreadsheet" in g or "report" in g) and not any(
                k in g for k in ("update", "append", "sync", "write", "log", "add row")),
            "scrape": any(k in g for k in ("scrape", "portal", "web ", "website", "crawl",
                                           "table", "inventory", "html")),
            "update_lead": has_update_word or any(k in g for k in (
                "update lead", "enrich", "reassign", "recalibrat", "calibrat",
                "recalculat", "status to", "re-engag", "nurtur")),
            "deal": ("deal" in g or "opportunity" in g or "contract" in g),
            "sheet_write": any(k in g for k in ("sheet", "spreadsheet", "tracking", "log ",
                                                "sync", "snapshot", "append", "dashboard",
                                                "summary", "report", "briefing", "analytics")),
            "form": bool(re.search(r"\bform\b|intake|onboard|submit|signup|sign up|"
                                   r"register|synchron", g)),
            "charge": any(k in g for k in ("charg", "autopay", "auto-pay", "payment amount",
                                           "capture payment", "process payment", "refund")),
            "email": any(k in g for k in ("email", "reminder", "notify", "notification",
                                          "dispatch", "notice", "outreach", "message",
                                          "follow-up", "followup", "alert")),
        }

    def _extract_params(self, goal: str, g: str) -> Dict[str, Any]:
        """Pull concrete entities (IDs, amounts, thresholds) out of the goal text."""
        amount = self._extract(r"([\d][\d,]*(?:\.\d+)?)\s*(?:k\b|usd|dollars)?", g,
                               default=8900.0, cast=lambda x: float(x.replace(",", "")))
        if "k" in g and amount and 0 < amount < 1000:
            amount *= 1000
        return {
            "min_score": self._extract(r"score\s*(?:>=|>|at least)\s*(\d+)", g, cast=int),
            "lead_id": self._extract(r"(lead-\d+)", g, default="LEAD-104", cast=str.upper),
            "invoice_id": self._extract(r"(inv[-\u2011]?[\d\-]+)", goal,
                                        default="INV-2026-003", cast=str.upper),
            "amount": amount,
            "to_email": self._extract(r"([\w.\-]+@[\w.\-]+\.\w+)", goal,
                                      default="psharma@solargrid.in", cast=str),
            "sheet_name": ("Audit Trail Log" if "audit" in g else "Executive Ops Summary"),
        }


    def _plan_heuristic(self, goal: str) -> List[WorkflowStep]:
        """
        Compose a dependency-aware plan from detected operational intents.
        Read intents run first (parallel-safe), mutations after, irreversible
        actions (email dispatch / charges) always last behind the HITL gate.
        """
        g = goal.lower()
        intents = self._detect_intents(g)
        p = self._extract_params(goal, g)

        # Ground any write/critical intent in at least one fetched data source so
        # the DAG always starts with observable read work (never a naked mutation).
        read_intent_present = any(intents[k] for k in ("invoices", "leads", "scrape", "sheet_read"))
        mutation_intent_present = any(
            intents[k] for k in ("update_lead", "deal", "sheet_write", "form", "charge", "email"))
        if mutation_intent_present and not read_intent_present:
            intents["leads"] = True

        reads: List[WorkflowStep] = []
        writes: List[WorkflowStep] = []
        criticals: List[WorkflowStep] = []

        # --- read intents (parallel-safe roots) -------------------------------
        if intents["invoices"]:
            status = "OVERDUE" if "overdue" in g else ("PAID" if "paid" in g else "PENDING")
            reads.append(WorkflowStep(
                id="step-R1", name="Query Billing Invoices",
                description=f"Fetch {status} invoices from the Billing MCP server.",
                tool_type=ToolType.MCP_TOOL, tool_name="billing_get_invoices",
                parameters={"status": status}, dependencies=[]))
        if intents["leads"]:
            params: Dict[str, Any] = {}
            if p["min_score"] is not None:
                params["min_score"] = p["min_score"]
            elif "qualified" in g:
                params["status"] = "QUALIFIED"
            reads.append(WorkflowStep(
                id="step-R2", name="Query CRM Leads",
                description="Retrieve matching lead records from the CRM MCP server.",
                tool_type=ToolType.MCP_TOOL, tool_name="crm_get_leads",
                parameters=params, dependencies=[]))
        if intents["scrape"]:
            reads.append(WorkflowStep(
                id="step-R3", name="Scrape Portal Data Table",
                description="Extract structured records from the target web portal DOM.",
                tool_type=ToolType.BROWSER, tool_name="scrape_table",
                parameters={"table_selector": "#portal-data-table"}, dependencies=[]))
        if intents["sheet_read"]:
            reads.append(WorkflowStep(
                id="step-R4", name="Read Tracking Sheet",
                description=f"Read rows from sheet '{p['sheet_name']}'.",
                tool_type=ToolType.MCP_TOOL, tool_name="sheets_get_data",
                parameters={"sheet_name": p["sheet_name"]}, dependencies=[]))

        read_deps = [r.id for r in reads] or []

        # --- mutation intents (depend on reads) -------------------------------
        if intents["update_lead"]:
            updates: Dict[str, Any] = {}
            if "qualified" in g:
                updates["status"] = "QUALIFIED"
            if p["min_score"] is not None:
                updates["score"] = p["min_score"]
            if not updates:
                updates["notes"] = f"Updated by NexusFlow workflow: {goal[:80]}"
            writes.append(WorkflowStep(
                id="step-W1", name="Update CRM Lead Record",
                description=f"Apply enrichment updates to lead {p['lead_id']}.",
                tool_type=ToolType.MCP_TOOL, tool_name="crm_update_lead",
                parameters={"lead_id": p["lead_id"], "updates": updates},
                dependencies=read_deps))
        if intents["deal"]:
            writes.append(WorkflowStep(
                id="step-W2", name="Create Enterprise Deal",
                description=f"Create sales deal worth ${p['amount']:,.0f} in the CRM.",
                tool_type=ToolType.MCP_TOOL, tool_name="crm_create_deal",
                parameters={"lead_id": p["lead_id"],
                            "title": f"Enterprise Deal for {p['lead_id']}",
                            "amount": p["amount"], "stage": "Contract Review"},
                dependencies=read_deps))
        if intents["sheet_write"]:
            writes.append(WorkflowStep(
                id="step-W3", name="Update Tracking Sheet",
                description=f"Append reconciled results to sheet '{p['sheet_name']}'.",
                tool_type=ToolType.MCP_TOOL, tool_name="sheets_append_row",
                parameters={"sheet_name": p["sheet_name"],
                            "row_data": {"Account": "SolarGrid India", "Region": "APAC",
                                         "ARR": p["amount"], "Health": "Amber",
                                         "Action Required": f"Auto: {goal[:48]}"}},
                dependencies=read_deps))
        if intents["form"]:
            writes.append(WorkflowStep(
                id="step-W4", name="Submit Web Portal Form",
                description="Fill and submit the portal intake form (self-healing enabled).",
                tool_type=ToolType.BROWSER, tool_name="fill_form_and_click",
                parameters={"form_data": {"company_name": "SolarGrid India",
                                          "contact_email": p["to_email"]},
                            "target_button_selector": "#submit-lead-btn",
                            "semantic_intent": "Submit Lead Sync"},
                dependencies=read_deps))

        write_deps = [w.id for w in writes] or read_deps


        # --- irreversible intents (always last, always behind HITL gate) ------
        if intents["charge"]:
            criticals.append(WorkflowStep(
                id="step-C1", name="Charge Customer Invoice",
                description=f"Execute payment charge of ${p['amount']:,.2f} against {p['invoice_id']}.",
                tool_type=ToolType.MCP_TOOL, tool_name="billing_charge_invoice",
                parameters={"invoice_id": p["invoice_id"], "amount": p["amount"]},
                dependencies=write_deps))
        if intents["email"]:
            criticals.append(WorkflowStep(
                id="step-C2", name="Dispatch Outbound Email",
                description=f"Send operational notice to {p['to_email']}.",
                tool_type=ToolType.MCP_TOOL, tool_name="email_send_reminder",
                parameters={"to_email": p["to_email"],
                            "subject": f"NexusFlow Notice regarding {p['invoice_id']}",
                            "body": f"Operational notice generated for goal: {goal[:140]}"},
                dependencies=write_deps))

        # --- fallback: goal mentions none of the intents ----------------------
        if not (reads or writes or criticals):
            reads.append(WorkflowStep(
                id="step-R1", name="Fetch Qualified Leads",
                description="Retrieve qualified leads with score >= 90 from CRM.",
                tool_type=ToolType.MCP_TOOL, tool_name="crm_get_leads",
                parameters={"min_score": 90}, dependencies=[]))
            writes.append(WorkflowStep(
                id="step-W1", name="Log Result to Tracking Sheet",
                description="Append the plan output to the executive sheet.",
                tool_type=ToolType.MCP_TOOL, tool_name="sheets_append_row",
                parameters={"sheet_name": "Executive Ops Summary",
                            "row_data": {"Account": "Auto-Planned",
                                         "Action Required": goal[:48]}},
                dependencies=["step-R1"]))

        steps = reads + writes + criticals
        # Renumber to step-1..N preserving dependency topology
        id_map = {s.id: f"step-{i + 1}" for i, s in enumerate(steps)}
        for s in steps:
            s.dependencies = [id_map[d] for d in s.dependencies if d in id_map]
            s.id = id_map[s.id]
        return steps


planner = GoalToDAGPlanner()
