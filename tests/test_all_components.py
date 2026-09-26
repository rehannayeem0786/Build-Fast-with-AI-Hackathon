import asyncio
import pytest

from app.core.planner import planner
from app.core.guardrail import safeguard
from app.core.orchestrator import orchestrator
from app.core.models import (
    RiskLevel, StepStatus, HumanApprovalDecision, WorkflowStep, ToolType, WorkflowDAG,
)
from app.agents.mcp_hub import mcp_hub
from app.agents.browser_agent import browser_agent
from app.mcp.client import mcp_client


# ----------------------------------------------------------------------
# Planner
# ----------------------------------------------------------------------
def test_dag_planner():
    goal = ("Reconcile overdue invoices in Stripe with HubSpot leads, update the "
            "tracking sheet, and queue reminder emails for approval")
    dag = planner.plan_workflow(goal)
    assert dag is not None
    assert dag.total_steps >= 3
    assert any(s.requires_human_approval for s in dag.steps)
    assert any(s.risk_level == RiskLevel.CRITICAL for s in dag.steps)
    # Irreversible email step must be the last dependency sink
    email_steps = [s for s in dag.steps if s.tool_name == "email_send_reminder"]
    assert email_steps, "email dispatch must be planned"
    assert email_steps[-1].requires_human_approval


def test_dag_planner_arbitrary_goal():
    """A goal outside canned scenarios must still produce a valid plan."""
    goal = "Pull fresh leads from the CRM and log this week's churn summary to the sheet"
    dag = planner.plan_workflow(goal)
    assert dag.total_steps >= 2
    ids = {s.id for s in dag.steps}
    for s in dag.steps:
        for dep in s.dependencies:
            assert dep in ids, f"dangling dependency {dep}"
    # No step may depend on a later step (acyclic in list order)
    order = {s.id: i for i, s in enumerate(dag.steps)}
    for s in dag.steps:
        for dep in s.dependencies:
            assert order[dep] < order[s.id]


def test_dag_planner_dependencies_topology():
    goal = ("Reconcile overdue invoices, update the tracking sheet, "
            "and queue reminder emails")
    dag = planner.plan_workflow(goal)
    assert dag.total_steps >= 3
    # First step has no dependencies
    assert dag.steps[0].dependencies == []
    # Writes depend on at least one read
    write_steps = [s for s in dag.steps if s.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)]
    assert all(s.dependencies for s in write_steps), "mutations must depend on upstream reads"


# ----------------------------------------------------------------------
# MCP hub + guardrail
# ----------------------------------------------------------------------
def test_mcp_hub_tools():
    leads = mcp_hub.execute_tool("crm_get_leads", {"status": "QUALIFIED"})
    assert "leads" in leads and len(leads["leads"]) > 0

    invoices = mcp_hub.execute_tool("billing_get_invoices", {"status": "OVERDUE"})
    assert "invoices" in invoices and len(invoices["invoices"]) > 0

    sheet_data = mcp_hub.execute_tool("sheets_get_data", {"sheet_name": "Executive Ops Summary"})
    assert "rows" in sheet_data


def test_mcp_tool_catalog_complete():
    """Every registered tool must expose a documented input schema."""
    defs = mcp_hub.list_mcp_tools()
    names = {d["name"] for d in defs}
    assert names == set(mcp_hub.tools.keys()), "tool catalog must match registered tools"
    for d in defs:
        assert d["description"], f"{d['name']} missing description"
        assert d["parameters"].get("properties"), f"{d['name']} missing properties"


def test_safeguard_risk_classification():
    risk, req_app = safeguard.assess_risk("billing_charge_invoice", {"invoice_id": "INV-1"})
    assert risk == RiskLevel.CRITICAL
    assert req_app is True

    risk_read, req_app_read = safeguard.assess_risk("crm_get_leads", {})
    assert risk_read == RiskLevel.LOW
    assert req_app_read is False


def test_safeguard_diff_preview_shape():
    step = WorkflowStep(
        id="step-1", name="Send email", description="dispatch",
        tool_type=ToolType.MCP_TOOL, tool_name="email_send_reminder",
        parameters={"to_email": "a@b.com", "subject": "s", "body": "b"},
        risk_level=RiskLevel.CRITICAL, requires_human_approval=True,
    )
    req = safeguard.generate_approval_request("wf-1", step, {})
    assert req.diff_before and req.diff_after
    assert req.risk_level == RiskLevel.CRITICAL
    assert req.description



# ----------------------------------------------------------------------
# Self-healing browser engine (real Playwright)
# ----------------------------------------------------------------------
async def test_self_healing_browser_agent():
    browser_agent.set_dom_version("v1")
    try:
        res1 = await browser_agent.fill_form_and_click(
            workflow_id="test-wf-1", step_id="step-1",
            form_data={"company_name": "SolarGrid"},
            target_button_selector="#submit-lead-btn",
            semantic_intent="Submit Lead Sync")
        assert res1["success"] is True
        assert res1["self_healed"] is False
        assert res1["engine"] == "PLAYWRIGHT", "real Chromium must be used"
        assert res1["clicked"] is True

        # Mutated DOM v2: primary selector breaks -> self-healing cascade
        browser_agent.set_dom_version("v2")
        res2 = await browser_agent.fill_form_and_click(
            workflow_id="test-wf-2", step_id="step-2",
            form_data={"company_name": "SolarGrid"},
            target_button_selector="#submit-lead-btn",
            semantic_intent="Submit Lead Sync v2")
        assert res2["success"] is True
        assert res2["self_healed"] is True
        assert res2["strategy"] in (
            "SEMANTIC_TEXT_GROUNDING", "ACCESSIBILITY_TREE_GROUNDING",
            "FORM_PROXIMITY_HEURISTIC", "LEARNED_MEMORY")
    finally:
        await browser_agent.close()


async def test_scrape_table_live_dom():
    browser_agent.set_dom_version("v1")
    try:
        rows = await browser_agent.scrape_table("#portal-data-table")
        assert len(rows) >= 1, "live DOM must yield scraped rows"
        assert all(isinstance(r, dict) for r in rows)
    finally:
        await browser_agent.close()


# ----------------------------------------------------------------------
# Real MCP transport (stdio handshake + tools/call)
# ----------------------------------------------------------------------
async def test_mcp_stdio_roundtrip():
    try:
        connected = await mcp_client.connect()
        if not connected:
            pytest.skip("MCP subprocess transport unavailable in this environment")
        assert mcp_client.transport == "MCP_STDIO"
        tools = await mcp_client.list_tools()
        assert len(tools) >= 11, "all tools must be advertised over MCP"

        result = await mcp_client.call_tool("crm_get_leads", {"status": "QUALIFIED"})
        assert result.get("_transport") == "MCP_STDIO"
        assert result.get("count", 0) >= 1
    finally:
        await mcp_client.close()


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------
async def test_full_orchestration_auto_approve():
    goal = ("Fetch top-tier qualified leads with score >= 90 from CRM, create "
            "enterprise deal, sync to executive sheet, and dispatch contract notice")
    dag = planner.plan_workflow(goal)
    res = await orchestrator.run_workflow(dag, auto_approve_all=True)
    assert res["status"] == "COMPLETED"
    assert res["completed_steps"] == dag.total_steps


def test_topological_levels_parallel_independent_reads():
    steps = [
        WorkflowStep(id="a", name="A", description="", tool_type=ToolType.MCP_TOOL,
                     tool_name="crm_get_leads", dependencies=[]),
        WorkflowStep(id="b", name="B", description="", tool_type=ToolType.MCP_TOOL,
                     tool_name="billing_get_invoices", dependencies=[]),
        WorkflowStep(id="c", name="C", description="", tool_type=ToolType.MCP_TOOL,
                     tool_name="sheets_append_row", dependencies=["a", "b"]),
    ]
    dag = WorkflowDAG(workflow_id="wf-topo", goal="t", steps=steps, total_steps=3)
    levels = orchestrator._topological_levels(dag)
    assert [sorted(s.id for s in lv) for lv in levels] == [["a", "b"], ["c"]]


# ----------------------------------------------------------------------
# SafeGuard HITL: reject / timeout / modify
# ----------------------------------------------------------------------
async def test_hitl_reject_aborts_without_side_effects():
    """A rejected CRITICAL step must abort the workflow with zero side effects."""
    goal = "Dispatch overdue notice email to the customer about invoice INV-2026-003"
    dag = planner.plan_workflow(goal)
    email_step = next(s for s in dag.steps if s.tool_name == "email_send_reminder")

    async def reject_soon():
        while email_step.id not in orchestrator.approval_futures:
            await asyncio.sleep(0.02)
        orchestrator.submit_approval_decision(HumanApprovalDecision(
            workflow_id=dag.workflow_id, step_id=email_step.id,
            decision="REJECT", comment="Do not send"))

    driver = asyncio.create_task(reject_soon())
    res = await orchestrator.run_workflow(dag, auto_approve_all=False,
                                          approval_timeout_sec=10)
    await driver

    assert res["status"] == "ABORTED"
    assert email_step.status == StepStatus.REJECTED


async def test_hitl_timeout_fails_safe():
    """No human decision -> deny-by-default within the timeout (never hangs)."""
    goal = "Charge the overdue invoice INV-2026-001 with the customer card"
    dag = planner.plan_workflow(goal)
    charge_step = next(s for s in dag.steps if s.tool_name == "billing_charge_invoice")

    res = await orchestrator.run_workflow(dag, auto_approve_all=False,
                                          approval_timeout_sec=0.5)
    assert res["status"] == "ABORTED"
    assert charge_step.status == StepStatus.REJECTED
    # Side effect check: invoice must remain uncharged in the billing mock
    from app.mock_apps.billing_server import mock_billing
    inv = next(i for i in mock_billing.get_invoices(status=None)
               if i["id"] == "INV-2026-001")
    assert inv.get("status") != "PAID", "timeout must not execute the charge"


async def test_hitl_modify_applies_params():
    """MODIFY must apply human-edited parameters before execution."""
    goal = "Dispatch reminder email about invoice INV-2026-003"
    dag = planner.plan_workflow(goal)
    email_step = next(s for s in dag.steps if s.tool_name == "email_send_reminder")

    async def modify_soon():
        while email_step.id not in orchestrator.approval_futures:
            await asyncio.sleep(0.02)
        orchestrator.submit_approval_decision(HumanApprovalDecision(
            workflow_id=dag.workflow_id, step_id=email_step.id,
            decision="MODIFY",
            modified_params={"subject": "HUMAN-EDITED SUBJECT"},
            comment="tighten subject"))

    driver = asyncio.create_task(modify_soon())
    res = await orchestrator.run_workflow(dag, auto_approve_all=False,
                                          approval_timeout_sec=10)
    await driver

    assert res["status"] == "COMPLETED"
    assert email_step.parameters["subject"] == "HUMAN-EDITED SUBJECT"
    assert email_step.status in (StepStatus.SUCCESS, StepStatus.RECOVERED, StepStatus.APPROVED)


# ----------------------------------------------------------------------
# API surface
# ----------------------------------------------------------------------
def test_fastapi_plan_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/plan", json={"goal": "Scrape the portal and update the CRM"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_steps"] >= 2
    assert body["planner_mode"] in ("LLM", "HEURISTIC")

    resp_tools = client.get("/api/mcp/tools")
    assert resp_tools.status_code == 200
    assert len(resp_tools.json()["tools"]) >= 11


# ----------------------------------------------------------------------
# Undo / rollback (compensating actions)
# ----------------------------------------------------------------------
async def test_undo_sheet_append():
    """A completed sheet mutation must be reversible via rollback."""
    connected = await mcp_client.connect()
    if not connected:
        pytest.skip("MCP subprocess transport unavailable in this environment")
    try:
        before = await mcp_client.call_tool(
            "sheets_get_data", {"sheet_name": "Executive Ops Summary"})
        rows_before = len(before.get("rows", []))

        dag = planner.plan_workflow("Append the weekly progress row to the tracking sheet")
        res = await orchestrator.run_workflow(dag, auto_approve_all=True)
        assert res["status"] == "COMPLETED"

        mid = await mcp_client.call_tool(
            "sheets_get_data", {"sheet_name": "Executive Ops Summary"})
        assert len(mid.get("rows", [])) == rows_before + 1, "append must add a row"

        undo = await orchestrator.rollback_workflow(dag.workflow_id)
        assert undo["status"] == "UNDONE", undo
        assert undo["undone"] >= 1

        after = await mcp_client.call_tool(
            "sheets_get_data", {"sheet_name": "Executive Ops Summary"})
        assert len(after.get("rows", [])) == rows_before, "rollback must remove the row"
    finally:
        await mcp_client.close()



# ----------------------------------------------------------------------
# LLM planner path (Groq / OpenRouter) — mocked, no network
# ----------------------------------------------------------------------
def test_llm_planner_produces_validated_plan(monkeypatch):
    """A well-formed LLM response is adopted as the plan (mode=LLM)."""
    import json as _json
    from app.core.planner import GoalToDAGPlanner
    from app.config import settings

    p = GoalToDAGPlanner()
    fake_response = _json.dumps({"steps": [
        {"id": "step-1", "name": "Fetch leads", "description": "read CRM",
         "tool_name": "crm_get_leads", "parameters": {"min_score": 90},
         "dependencies": []},
        {"id": "step-2", "name": "Notify customer", "description": "email",
         "tool_name": "email_send_reminder",
         "parameters": {"to_email": "a@b.co", "subject": "s", "body": "b"},
         "dependencies": ["step-1"]},
    ]})
    monkeypatch.setattr(p, "_call_llm", lambda prompt: fake_response)
    monkeypatch.setattr(p, "_last_used_model", "groq:openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")

    dag = p.plan_workflow("whatever the goal is")
    assert dag.planner_mode == "LLM"
    assert dag.planner_model == "groq:openai/gpt-oss-120b"
    assert [s.tool_name for s in dag.steps] == ["crm_get_leads", "email_send_reminder"]
    # Risk calibration still applies to LLM-produced steps
    assert dag.steps[1].requires_human_approval is True


def test_llm_planner_rejects_hallucinated_tools(monkeypatch):
    """Unknown tool names force a safe fallback to the heuristic planner."""
    import json as _json
    from app.core.planner import GoalToDAGPlanner
    from app.config import settings

    p = GoalToDAGPlanner()
    fake_response = _json.dumps({"steps": [
        {"id": "step-1", "name": "Payroll", "description": "made up",
         "tool_name": "run_payroll", "parameters": {}, "dependencies": []},
    ]})
    monkeypatch.setattr(p, "_call_llm", lambda prompt: fake_response)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")

    dag = p.plan_workflow("Reconcile overdue invoices and notify the team")
    assert dag.planner_mode == "HEURISTIC"
    assert all(s.tool_name != "run_payroll" for s in dag.steps)


def test_llm_planner_fenced_json_parsing():
    """Model output wrapped in ```json fences is still parsed."""
    from app.core.planner import GoalToDAGPlanner
    fenced = 'Sure! Here is the plan:\n```json\n{"steps": []}\n```\nDone.'
    assert GoalToDAGPlanner._parse_json_loosely(fenced) == {"steps": []}


def test_force_heuristic_bypasses_llm(monkeypatch):
    """Benchmark reproducibility switch skips the LLM even with keys set."""
    from app.core.planner import GoalToDAGPlanner
    from app.config import settings

    p = GoalToDAGPlanner()
    p.force_heuristic = True
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    # If _call_llm were invoked it would be through the network; assert none.
    monkeypatch.setattr(
        p, "_call_llm",
        lambda prompt: (_ for _ in ()).throw(AssertionError("LLM called!")))

    dag = p.plan_workflow("Reconcile overdue invoices and queue reminders")
    assert dag.planner_mode == "HEURISTIC"


# ----------------------------------------------------------------------
# Inter-step dataflow (parameter reference resolution)
# ----------------------------------------------------------------------
def test_parameter_reference_resolution():
    """Explicit {{path}}, bare-name, and inline tokens all resolve upstream."""
    q = WorkflowStep(
        id="step-1", name="query", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="billing_get_invoices", status=StepStatus.SUCCESS,
        result={"count": 1, "invoices": [{"id": "INV-9", "amount_due": 42.5}]})
    p = WorkflowStep(
        id="step-2", name="prepare", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="billing_prepare_reminder", status=StepStatus.RUNNING,
        parameters={
            "invoice_id": "{{step-1.result.invoices[0].id}}",   # explicit path
            "alt": "{{invoice_id}}",                            # bare-name safety net
            "notes": "About <invoice_id> amount $<amount>",     # inline in text
        })
    dag = WorkflowDAG(workflow_id="wf-df", goal="g", steps=[q, p], total_steps=2)

    resolved, mapping = orchestrator._resolve_parameters(p, dag)
    assert resolved["invoice_id"] == "INV-9"
    assert resolved["alt"] == "INV-9"
    assert resolved["notes"] == "About INV-9 amount $42.5"   # amount -> amount_due
    assert len(mapping) >= 2


def test_unresolved_reference_fails_fast():
    """An exact placeholder with no upstream data raises a clear error."""
    p = WorkflowStep(
        id="step-1", name="prepare", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="billing_prepare_reminder", status=StepStatus.RUNNING,
        parameters={"invoice_id": "<invoice_id>"})
    dag = WorkflowDAG(workflow_id="wf-df2", goal="g", steps=[p], total_steps=1)
    with pytest.raises(ValueError, match="Unresolved parameter reference"):
        orchestrator._resolve_parameters(p, dag)


def test_path_variant_reference_resolution():
    """Model guesses like result.deal_id resolve to result.deal.id."""
    deal_step = WorkflowStep(
        id="step-1", name="create deal", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="crm_create_deal", status=StepStatus.SUCCESS,
        result={"success": True, "deal": {"id": "DEAL-504", "lead_id": "LEAD-104"}})
    log_step = WorkflowStep(
        id="step-2", name="log", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="sheets_append_row", status=StepStatus.RUNNING,
        parameters={"row_data": {"deal_id": "{{step-1.result.deal_id}}",
                                 "lead": "{{step-1.result.deal.lead_id}}"}})
    dag = WorkflowDAG(workflow_id="wf-pv", goal="g",
                      steps=[deal_step, log_step], total_steps=2)

    resolved, _mapping = orchestrator._resolve_parameters(log_step, dag)
    assert resolved["row_data"]["deal_id"] == "DEAL-504"   # deal_id -> deal.id
    assert resolved["row_data"]["lead"] == "LEAD-104"       # exact nested path


async def test_dataflow_reference_end_to_end():
    """A plan wired with {{step-1.result...}} executes and passes the value."""
    q = WorkflowStep(
        id="step-1", name="Query invoices", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="billing_get_invoices", parameters={"status": "OVERDUE"},
        dependencies=[])
    p = WorkflowStep(
        id="step-2", name="Prepare payload", description="", tool_type=ToolType.MCP_TOOL,
        tool_name="billing_prepare_reminder",
        parameters={"invoice_id": "{{step-1.result.invoices[0].id}}"},
        dependencies=["step-1"])
    dag = WorkflowDAG(workflow_id="wf-df3",
                      goal="Prepare reminders for overdue invoices",
                      steps=[q, p], total_steps=2)

    res = await orchestrator.run_workflow(dag, auto_approve_all=True)
    assert res["status"] == "COMPLETED"
    assert p.status == StepStatus.SUCCESS
    assert p.result["invoice_details"]["id"].startswith("INV-")
    # The literal placeholder must be gone from the executed parameters
    assert p.parameters["invoice_id"].startswith("INV-")


