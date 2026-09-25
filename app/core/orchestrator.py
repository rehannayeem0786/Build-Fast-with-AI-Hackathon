import asyncio
import json
import re
import time
from typing import Dict, List, Any, Optional, Callable, Set, Tuple

from app.core.models import (
    WorkflowDAG, WorkflowStep, StepStatus, RiskLevel,
    HumanApprovalRequest, HumanApprovalDecision, ToolType,
)
from app.core.telemetry import telemetry
from app.core.guardrail import safeguard
from app.mcp.client import mcp_client
from app.agents.browser_agent import browser_agent
from app.config import settings

# Sentinel for "reference did not resolve"
_MISSING = object()

# {{step-1.result.invoices[0].id}} or {{step-1.invoices[0].id}} or bare {{invoice_id}}
_REF_EXACT = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")
_ANGLE_EXACT = re.compile(r"^<([\w.\[\]-]+)>$")
_REF_INLINE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_ANGLE_INLINE = re.compile(r"<([\w][\w.\-]*)>")
_PATH_RE = re.compile(r"^(step-[\w]+)(?:\.result)?(?:\.(.+))?$")
_SCALAR = (str, int, float, bool)

# Terminal step states that block dependent steps.
BLOCKING_FAILURE_STATES = {StepStatus.FAILED, StepStatus.REJECTED, StepStatus.SKIPPED}


class WorkflowOrchestrator:
    """
    DAG Workflow Orchestrator State Machine.

    Executes dependency-aware DAGs level-by-level (independent steps run in
    parallel), coordinates MCP and Browser tools through real transports,
    retries transient failures, pauses at SafeGuard Human Gates with a
    fail-safe timeout, and supports APPROVE / MODIFY / REJECT decisions.
    """

    def __init__(self):
        self.active_workflows: Dict[str, WorkflowDAG] = {}
        self.pending_approvals: Dict[str, HumanApprovalRequest] = {}
        self.approval_futures: Dict[str, asyncio.Future] = {}
        self.event_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        # Compensating-action log per workflow (enables undo/rollback)
        self.undo_logs: Dict[str, List[Dict[str, Any]]] = {}

    def register_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self.event_callbacks.append(cb)

    async def emit_event(self, event_type: str, data: Dict[str, Any]):
        payload = {"event": event_type, "timestamp": time.time(), "data": data}
        for cb in self.event_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                print(f"[ERROR] Event callback error: {e}")

    # ------------------------------------------------------------------
    # DAG topology
    # ------------------------------------------------------------------
    @staticmethod
    def _topological_levels(dag: WorkflowDAG) -> List[List[WorkflowStep]]:
        """
        Partition steps into dependency levels. Steps within the same level
        have no dependencies on each other and may execute in parallel.
        Unknown dependencies are ignored; cycles degrade to remaining order.
        """
        valid_ids: Set[str] = {s.id for s in dag.steps}
        remaining = {s.id: set(d for d in s.dependencies if d in valid_ids and d != s.id)
                     for s in dag.steps}
        by_id = {s.id: s for s in dag.steps}
        levels: List[List[WorkflowStep]] = []
        done: Set[str] = set()

        while remaining:
            ready_ids = [sid for sid, deps in remaining.items() if deps <= done]
            if not ready_ids:
                # Cycle or unsatisfiable deps — flush remaining in listed order
                ready_ids = list(remaining.keys())
            levels.append([by_id[sid] for sid in ready_ids])
            for sid in ready_ids:
                del remaining[sid]
            done.update(ready_ids)

        return levels


    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------
    async def run_workflow(
        self,
        dag: WorkflowDAG,
        auto_approve_all: bool = False,
        approval_timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute a DAG. Independent steps run in parallel per dependency level.
        SafeGuard-gated steps pause for a human decision with a fail-safe
        timeout (default from settings) that auto-REJECTs to prevent hangs.
        """
        self.active_workflows[dag.workflow_id] = dag
        # Auto-declare dependencies implied by {{step-X...}} parameter refs
        self._wire_implicit_dependencies(dag)
        telemetry.start_trace(dag)

        await self.emit_event("WORKFLOW_STARTED", {
            "workflow_id": dag.workflow_id,
            "goal": dag.goal,
            "total_steps": dag.total_steps,
            "planner_mode": dag.planner_mode,
            "planner_model": dag.planner_model,
        })

        # Ensure real MCP transport is available (falls back to local hub).
        # Track ownership: if WE open the session here, we close it before
        # returning so no background tasks outlive the caller's event loop
        # (prevents hangs when callers use asyncio.run per invocation).
        mcp_reused = mcp_client._session_usable()
        if not mcp_reused:
            await mcp_client.connect()
        browser_reused = browser_agent._page is not None

        try:
            return await self._execute_dag(
                dag, auto_approve_all, approval_timeout_sec
            )
        finally:
            if not mcp_reused and mcp_client.connected:
                await mcp_client.close()
            if not browser_reused and browser_agent._page is not None:
                await browser_agent.close()

    async def _execute_dag(
        self,
        dag: WorkflowDAG,
        auto_approve_all: bool,
        approval_timeout_sec: Optional[float],
    ) -> Dict[str, Any]:
        dag.overall_status = "RUNNING"
        aborted = False

        for level in self._topological_levels(dag):
            # Skip steps whose dependencies failed/rejected/skipped
            runnable: List[WorkflowStep] = []
            for step in level:
                dep_ids = set(step.dependencies)
                blocked = any(
                    s.status in BLOCKING_FAILURE_STATES
                    for s in dag.steps if s.id in dep_ids
                )
                if blocked:
                    step.status = StepStatus.SKIPPED
                    telemetry.complete_step(dag.workflow_id, step, StepStatus.SKIPPED,
                                            error="Upstream dependency blocked")
                    await self.emit_event("STEP_SKIPPED", {
                        "workflow_id": dag.workflow_id,
                        "step_id": step.id,
                        "reason": "Upstream dependency failed or was rejected",
                    })
                else:
                    runnable.append(step)

            if not runnable:
                continue

            if aborted:
                for step in runnable:
                    step.status = StepStatus.SKIPPED
                    telemetry.complete_step(dag.workflow_id, step, StepStatus.SKIPPED,
                                            error="Workflow aborted by human rejection")
                    await self.emit_event("STEP_SKIPPED", {
                        "workflow_id": dag.workflow_id,
                        "step_id": step.id,
                        "reason": "Workflow aborted by human rejection",
                    })
                continue

            results = await asyncio.gather(*[
                self._run_step(dag, step, auto_approve_all, approval_timeout_sec)
                for step in runnable
            ], return_exceptions=True)

            for step, result in zip(runnable, results):
                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = str(result)
                    telemetry.complete_step(dag.workflow_id, step, StepStatus.FAILED,
                                            error=str(result))
                    await self.emit_event("STEP_FAILED", {
                        "workflow_id": dag.workflow_id,
                        "step_id": step.id,
                        "error": str(result),
                    })
                elif result == "ABORTED":
                    aborted = True

        # ------------------------------------------------------------------
        # Final status determination
        # ------------------------------------------------------------------
        statuses = [s.status for s in dag.steps]
        if StepStatus.REJECTED in statuses:
            dag.overall_status = "ABORTED"
        elif StepStatus.FAILED in statuses or StepStatus.SKIPPED in statuses:
            dag.overall_status = "FAILED"
        else:
            dag.overall_status = "COMPLETED"

        dag.completed_steps = sum(
            1 for s in dag.steps
            if s.status in (StepStatus.SUCCESS, StepStatus.RECOVERED, StepStatus.APPROVED)
        )
        trace_path = telemetry.finish_trace(dag.workflow_id, dag.overall_status)

        await self.emit_event("WORKFLOW_COMPLETED", {
            "workflow_id": dag.workflow_id,
            "status": dag.overall_status,
            "completed_steps": dag.completed_steps,
            "total_steps": dag.total_steps,
            "trace_path": trace_path,
            "mcp_transport": mcp_client.transport,
        })

        return {
            "workflow_id": dag.workflow_id,
            "status": dag.overall_status,
            "completed_steps": dag.completed_steps,
            "total_steps": dag.total_steps,
            "mcp_transport": mcp_client.transport,
            "trace_path": trace_path,
        }

    # ------------------------------------------------------------------
    # Inter-step dataflow (parameter reference resolution)
    # ------------------------------------------------------------------
    @staticmethod
    def _walk_path(root: Any, path: str) -> Any:
        """Walk 'invoices[0].id' style paths over a result object."""
        cur = root
        for token in re.findall(r"[^.\[\]]+|\[\d+\]", path):
            if token.startswith("["):
                if not isinstance(cur, list):
                    return _MISSING
                idx = int(token[1:-1])
                if idx >= len(cur):
                    return _MISSING
                cur = cur[idx]
            else:
                if not isinstance(cur, dict) or token not in cur:
                    return _MISSING
                cur = cur[token]
        return cur

    @classmethod
    def _iter_key_hits(cls, node: Any, want_keys: Set[str]):
        """BFS for dict keys in want_keys; yields (key, value) in document order."""
        queue = [node]
        while queue:
            cur = queue.pop(0)
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k in want_keys:
                        yield k, v
                    queue.append(v)
            elif isinstance(cur, list):
                queue.extend(cur)

    @classmethod
    def _iter_prefix_hits(cls, node: Any, prefix: str):
        """BFS for dict keys starting with prefix whose value is scalar."""
        queue = [node]
        while queue:
            cur = queue.pop(0)
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k.startswith(prefix) and isinstance(v, _SCALAR):
                        yield k, v
                    queue.append(v)
            elif isinstance(cur, list):
                queue.extend(cur)

    @classmethod
    def _find_upstream_value(
        cls, name: str, earlier: List[Tuple[str, Any]]
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Resolve a BARE placeholder name (e.g. 'invoice_id', 'lead_id', 'amount')
        against results of already-completed earlier steps:
          1. exact scalar key match     (invoice_id -> key 'invoice_id')
          2. id-container heuristic     (invoice_id -> invoices[0].id,
                                         lead_id    -> leads[0].id)
          3. scalar key prefix match    (amount -> amount_due)
        """
        # 1) exact key, scalar value
        for src, res in earlier:
            for k, v in cls._iter_key_hits(res, {name}):
                if isinstance(v, _SCALAR):
                    return v, f"{src}.{k}"

        # 2) *_id -> plural/singular record container with an 'id' field
        if name.endswith("_id"):
            base = name[:-3]
            containers = {base + "s", base}
            for src, res in earlier:
                for k, v in cls._iter_key_hits(res, containers):
                    item, suffix = None, ""
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        item, suffix = v[0], "[0]"
                    elif isinstance(v, dict):
                        item = v
                    if item is not None and isinstance(item.get("id"), _SCALAR):
                        return item["id"], f"{src}.{k}{suffix}.id"

        # 3) prefix match (amount -> amount_due)
        if len(name) >= 4:
            for src, res in earlier:
                for k, v in cls._iter_prefix_hits(res, name):
                    return v, f"{src}.{k}"
        return None, None

    def _resolve_parameters(
        self, step: WorkflowStep, dag: WorkflowDAG
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Replace dataflow references in step.parameters with real values from
        earlier completed steps. Supported token forms (exact or inline):

            {{step-1.result.invoices[0].id}}   explicit path (preferred)
            {{step-1.invoices[0].id}}          shorthand ('.result' optional)
            {{invoice_id}} / <invoice_id>       bare name -> upstream search

        Returns (resolved_params, mapping_of_replacements).
        Raises ValueError when an EXACT (whole-string) token cannot resolve —
        such a parameter is functionally required, so failing fast with a
        clear message beats calling the tool with a literal placeholder.
        """
        step_index = dag.steps.index(step)
        earlier = [
            (s.id, s.result)
            for s in dag.steps[:step_index]
            if s.status in (StepStatus.SUCCESS, StepStatus.RECOVERED, StepStatus.APPROVED)
            and isinstance(s.result, dict)
        ]
        by_step = {sid: res for sid, res in earlier}
        mapping: Dict[str, Any] = {}

        def lookup(expr: str) -> Any:
            m = _PATH_RE.match(expr.strip())
            if m and m.group(1).startswith("step-"):
                sid, path = m.group(1), m.group(2)
                if sid not in by_step:
                    return _MISSING
                return by_step[sid] if not path else self._walk_path(by_step[sid], path)
            # bare name -> search earlier results
            val, _src = self._find_upstream_value(expr.strip(), earlier)
            return _MISSING if val is None else val

        def resolve(node: Any, key_path: str) -> Any:
            if isinstance(node, dict):
                return {k: resolve(v, f"{key_path}.{k}") for k, v in node.items()}
            if isinstance(node, list):
                return [resolve(v, f"{key_path}[{i}]") for i, v in enumerate(node)]
            if not isinstance(node, str):
                return node

            # Whole string is ONE token -> return the native value (may be number/list)
            exact = _REF_EXACT.match(node) or _ANGLE_EXACT.match(node)
            if exact:
                val = lookup(exact.group(1))
                if val is _MISSING:
                    raise ValueError(
                        f"Unresolved parameter reference '{node}' in step "
                        f"'{step.id}' ({key_path}): no value in completed earlier "
                        f"steps {[sid for sid, _ in earlier] or '[]'}. Reference "
                        f"upstream results, e.g. {{{{step-1.result.invoices[0].id}}}}."
                    )
                mapping[key_path] = val
                return val

            # Inline tokens inside longer text -> substitute what resolves,
            # leave the rest untouched (cosmetic text must not kill the run).
            def _sub(m: "re.Match") -> str:
                val = lookup(m.group(1))
                if val is _MISSING:
                    return m.group(0)
                mapping[key_path] = val
                return json.dumps(val) if isinstance(val, (dict, list)) else str(val)

            out = _REF_INLINE.sub(_sub, node)
            return _ANGLE_INLINE.sub(_sub, out)

        return resolve(step.parameters, step.id), mapping

    @staticmethod
    def _wire_implicit_dependencies(dag: WorkflowDAG) -> None:
        """
        Safety net for LLM plans that reference {{step-X...}} in parameters
        but forget to declare the dependency: add the referenced earlier step
        so it can never run in parallel with its data source.
        """
        order = {s.id: i for i, s in enumerate(dag.steps)}
        for s in dag.steps:
            try:
                exprs = _REF_INLINE.findall(json.dumps(s.parameters))
            except Exception:
                continue
            for expr in exprs:
                m = _PATH_RE.match(expr.strip())
                if not m:
                    continue
                src = m.group(1)
                if (src in order and order[src] < order[s.id]
                        and src not in s.dependencies):
                    s.dependencies.append(src)

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------
    async def _run_step(
        self,
        dag: WorkflowDAG,
        step: WorkflowStep,
        auto_approve_all: bool,
        approval_timeout_sec: Optional[float],
    ) -> Any:
        step.status = StepStatus.RUNNING
        telemetry.record_step_start(dag.workflow_id, step)

        await self.emit_event("STEP_STARTED", {
            "workflow_id": dag.workflow_id,
            "step_id": step.id,
            "name": step.name,
            "tool_type": step.tool_type.value,
            "risk_level": step.risk_level.value,
        })

        start_t = time.time()

        # 1. Inter-step dataflow — resolve {{step-N.result...}} / <placeholder>
        #    references BEFORE the gate so humans review resolved values.
        try:
            resolved, mapping = self._resolve_parameters(step, dag)
            if mapping:
                step.parameters = resolved
                pretty = ", ".join(f"{k}={v!r}" for k, v in list(mapping.items())[:4])
                telemetry.log_step_event(
                    dag.workflow_id, step.id,
                    f"Dataflow resolved {len(mapping)} reference(s): {pretty}",
                    level="INFO", metadata={"resolved": {k: str(v) for k, v in mapping.items()}},
                )
        except ValueError as e:
            # Unresolved required reference — fail fast, no pointless retries.
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration_ms = round((time.time() - start_t) * 1000, 2)
            telemetry.complete_step(dag.workflow_id, step, StepStatus.FAILED, error=str(e))
            await self.emit_event("STEP_FAILED", {
                "workflow_id": dag.workflow_id,
                "step_id": step.id,
                "error": str(e),
            })
            return "FAILED"

        # 2. SafeGuard Gate — pause for human decision on gated steps
        if step.requires_human_approval and not auto_approve_all:
            gate_result = await self._human_gate(dag, step, approval_timeout_sec)
            if gate_result in ("REJECTED", "TIMEOUT"):
                return "ABORTED"

        # 3. Execute with bounded retries (transient failure recovery)
        last_error: Optional[Exception] = None
        for attempt in range(settings.MAX_STEP_RETRIES + 1):
            try:
                result = await self._execute_tool(dag, step)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < settings.MAX_STEP_RETRIES:
                    telemetry.log_step_event(
                        dag.workflow_id, step.id,
                        f"Attempt {attempt + 1} failed ({e}). Retrying "
                        f"(attempt {attempt + 2}/{settings.MAX_STEP_RETRIES + 1})...",
                        level="WARN",
                    )
                    await asyncio.sleep(settings.STEP_RETRY_BACKOFF_SEC * (attempt + 1))
        if last_error is not None:
            step.status = StepStatus.FAILED
            step.error = str(last_error)
            step.duration_ms = round((time.time() - start_t) * 1000, 2)
            telemetry.complete_step(dag.workflow_id, step, StepStatus.FAILED,
                                    error=str(last_error))
            await self.emit_event("STEP_FAILED", {
                "workflow_id": dag.workflow_id,
                "step_id": step.id,
                "error": str(last_error),
            })
            return "FAILED"

        step.duration_ms = round((time.time() - start_t) * 1000, 2)
        step.result = result
        self._record_undo(dag, step, result)
        if isinstance(result, dict) and result.get("self_healed"):
            step.status = StepStatus.RECOVERED
            step.self_healing_attempts = 1
        else:
            step.status = StepStatus.SUCCESS

        telemetry.complete_step(dag.workflow_id, step, step.status, result=result)
        await self.emit_event("STEP_COMPLETED", {
            "workflow_id": dag.workflow_id,
            "step_id": step.id,
            "status": step.status.value,
            "duration_ms": step.duration_ms,
            "result": result,
        })

    async def _human_gate(
        self,
        dag: WorkflowDAG,
        step: WorkflowStep,
        approval_timeout_sec: Optional[float],
    ) -> str:
        """
        Pause for human authorization. Returns APPROVED | REJECTED | TIMEOUT.
        Fail-safe: when no decision arrives within the timeout, the action is
        REJECTED (deny-by-default) so a live demo can never hang.
        """
        step.status = StepStatus.WAITING_APPROVAL
        approval_req = safeguard.generate_approval_request(
            dag.workflow_id, step, current_system_state={})
        self.pending_approvals[step.id] = approval_req

        await self.emit_event("APPROVAL_REQUIRED", {
            "workflow_id": dag.workflow_id,
            "step_id": step.id,
            "request": approval_req.model_dump(),
        })

        timeout = approval_timeout_sec if approval_timeout_sec is not None \
            else settings.APPROVAL_TIMEOUT_SEC
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.approval_futures[step.id] = fut

        timed_out = False
        try:
            decision: HumanApprovalDecision = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            decision = HumanApprovalDecision(
                workflow_id=dag.workflow_id, step_id=step.id,
                decision="REJECT", comment="Auto-rejected: approval timeout (fail-safe).")
            await self.emit_event("APPROVAL_TIMEOUT", {
                "workflow_id": dag.workflow_id,
                "step_id": step.id,
                "timeout_sec": timeout,
                "message": "No human decision received — action denied by fail-safe.",
            })
        finally:
            self.pending_approvals.pop(step.id, None)
            self.approval_futures.pop(step.id, None)

        telemetry.record_hitl_event(
            dag.workflow_id, step.id, decision.decision,
            approval_req.diff_before, approval_req.diff_after)

        if decision.decision == "APPROVE":
            step.status = StepStatus.APPROVED
            await self.emit_event("APPROVAL_GRANTED", {
                "workflow_id": dag.workflow_id, "step_id": step.id,
            })
            return "APPROVED"

        if decision.decision == "MODIFY":
            # Apply human-modified parameters before execution
            if decision.modified_params:
                step.parameters.update(decision.modified_params)
                step.diff_preview = {"modified": decision.modified_params}
            step.status = StepStatus.APPROVED
            await self.emit_event("APPROVAL_MODIFIED", {
                "workflow_id": dag.workflow_id, "step_id": step.id,
                "modified_params": decision.modified_params,
            })
            await self.emit_event("APPROVAL_GRANTED", {
                "workflow_id": dag.workflow_id, "step_id": step.id,
            })
            return "APPROVED"

        # REJECT (explicit or timeout)
        step.status = StepStatus.REJECTED
        step.error = decision.comment or "Human rejected action"
        await self.emit_event("APPROVAL_REJECTED", {
            "workflow_id": dag.workflow_id, "step_id": step.id,
            "comment": decision.comment,
        })
        return "TIMEOUT" if timed_out else "REJECTED"

        return "OK"

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    async def _execute_tool(self, dag: WorkflowDAG, step: WorkflowStep) -> Any:
        """Route the step to the MCP transport or the browser engine."""
        await self.emit_event("TOOL_CALL", {
            "workflow_id": dag.workflow_id,
            "step_id": step.id,
            "tool_name": step.tool_name,
            "parameters": step.parameters,
        })

        if step.tool_type == ToolType.BROWSER:
            if step.tool_name == "scrape_table":
                rows = await browser_agent.scrape_table(
                    step.parameters.get("table_selector", "#portal-data-table"))
                return {"rows": rows, "count": len(rows), "engine": browser_agent.engine}

            if step.tool_name == "fill_form_and_click":
                return await browser_agent.fill_form_and_click(
                    workflow_id=dag.workflow_id,
                    step_id=step.id,
                    form_data=step.parameters.get("form_data", {}),
                    target_button_selector=step.parameters.get(
                        "target_button_selector", "#submit-lead-btn"),
                    semantic_intent=step.parameters.get("semantic_intent", "Submit"),
                )

            raise ValueError(f"Unknown browser tool '{step.tool_name}'.")

        # Default: MCP tool over the real MCP transport (or local fallback)
        return await mcp_client.call_tool(step.tool_name, step.parameters)

    # ------------------------------------------------------------------
    # Undo / rollback (compensating actions)
    # ------------------------------------------------------------------
    def _record_undo(self, dag: WorkflowDAG, step: WorkflowStep, result: Any) -> None:
        """Record an inverse action for reversible mutations."""
        if not isinstance(result, dict):
            return
        entry: Optional[Dict[str, Any]] = None

        if step.tool_name == "sheets_append_row" and result.get("row_number") is not None:
            entry = {
                "tool": step.tool_name, "step_id": step.id,
                "undo_tool": "sheets_delete_row",
                "params": {"sheet_name": result.get("sheet_name",
                                                    step.parameters.get("sheet_name")),
                           "row_number": result["row_number"]},
                "description": f"Delete row {result['row_number']} appended by this step",
            }
        elif step.tool_name == "crm_update_lead" and result.get("before"):
            before = {k: v for k, v in result["before"].items() if k != "id"}
            entry = {
                "tool": step.tool_name, "step_id": step.id,
                "undo_tool": "crm_update_lead",
                "params": {"lead_id": result.get("lead_id",
                                                 step.parameters.get("lead_id")),
                           "updates": before},
                "description": f"Restore lead {result.get('lead_id')} to its pre-run state",
            }

        if entry:
            self.undo_logs.setdefault(dag.workflow_id, []).append(entry)

    async def rollback_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Execute compensating actions in reverse order, restoring the state
        observed before each reversible mutation. Irreversible actions
        (emails, charges) are gated upstream precisely because they cannot
        be rolled back here.
        """
        log = self.undo_logs.get(workflow_id, [])
        if not log:
            return {"workflow_id": workflow_id, "status": "NOTHING_TO_UNDO", "undone": 0}

        undone: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []

        for entry in reversed(log):
            try:
                res = await mcp_client.call_tool(entry["undo_tool"], entry["params"])
                ok = bool(isinstance(res, dict) and
                          (res.get("success") is True or res.get("success") is None))
                (undone if ok else failures).append({
                    "step_id": entry["step_id"],
                    "undo_tool": entry["undo_tool"],
                    "description": entry["description"],
                    "result": res if isinstance(res, dict) else {"result": res},
                })
            except Exception as e:
                failures.append({"step_id": entry["step_id"],
                                 "undo_tool": entry["undo_tool"], "error": str(e)})

        self.undo_logs[workflow_id] = []
        status = "UNDONE" if not failures else "PARTIALLY_UNDONE"
        await self.emit_event("WORKFLOW_UNDONE", {
            "workflow_id": workflow_id,
            "status": status,
            "undone": len(undone),
            "failed": len(failures),
        })
        return {"workflow_id": workflow_id, "status": status,
                "undone": len(undone), "failed": len(failures),
                "actions": undone, "errors": failures}

    # ------------------------------------------------------------------
    # Human decision intake
    # ------------------------------------------------------------------
    def submit_approval_decision(self, decision: HumanApprovalDecision) -> bool:
        if decision.step_id in self.approval_futures:
            fut = self.approval_futures[decision.step_id]
            if not fut.done():
                fut.set_result(decision)
                return True
        return False


orchestrator = WorkflowOrchestrator()

