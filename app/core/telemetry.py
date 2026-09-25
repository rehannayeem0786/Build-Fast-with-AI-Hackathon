import os
import json
import time
from typing import Dict, List, Any, Optional
from app.core.models import WorkflowStep, WorkflowDAG, StepStatus, RiskLevel

class TelemetryLogger:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.active_traces: Dict[str, Dict[str, Any]] = {}

    def start_trace(self, dag: WorkflowDAG) -> Dict[str, Any]:
        trace_data = {
            "workflow_id": dag.workflow_id,
            "goal": dag.goal,
            "planner_mode": dag.planner_mode,
            "planner_model": dag.planner_model,
            "start_time": time.time(),
            "end_time": None,
            "total_duration_sec": 0.0,
            "status": "RUNNING",
            "steps": [],
            "self_healing_events": [],
            "hitl_events": [],
            # Honest cost: only LLM planning consumes tokens; heuristic = $0.
            "cost_usd": dag.estimated_cost_usd
        }
        self.active_traces[dag.workflow_id] = trace_data
        return trace_data

    def record_step_start(self, workflow_id: str, step: WorkflowStep):
        if workflow_id not in self.active_traces:
            return
        
        step_entry = {
            "step_id": step.id,
            "name": step.name,
            "tool_type": step.tool_type.value,
            "tool_name": step.tool_name,
            "parameters": step.parameters,
            "risk_level": step.risk_level.value,
            "requires_approval": step.requires_human_approval,
            "start_time": time.time(),
            "status": StepStatus.RUNNING.value,
            "logs": [],
            "retries": 0
        }
        self.active_traces[workflow_id]["steps"].append(step_entry)

    def log_step_event(self, workflow_id: str, step_id: str, message: str, level: str = "INFO", metadata: Optional[Dict[str, Any]] = None):
        if workflow_id not in self.active_traces:
            return
        
        timestamp = time.time()
        for step in self.active_traces[workflow_id]["steps"]:
            if step["step_id"] == step_id:
                step["logs"].append({
                    "timestamp": timestamp,
                    "level": level,
                    "message": message,
                    "metadata": metadata or {}
                })
                break

    def record_self_healing(self, workflow_id: str, step_id: str, failed_selector: str, recovery_strategy: str, recovered_selector: str, details: str):
        event = {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "timestamp": time.time(),
            "failed_selector": failed_selector,
            "recovery_strategy": recovery_strategy,
            "recovered_selector": recovered_selector,
            "details": details
        }
        if workflow_id in self.active_traces:
            self.active_traces[workflow_id]["self_healing_events"].append(event)

    def record_hitl_event(self, workflow_id: str, step_id: str, decision: str, diff_before: Any, diff_after: Any):
        event = {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "timestamp": time.time(),
            "decision": decision,
            "diff_before": diff_before,
            "diff_after": diff_after
        }
        if workflow_id in self.active_traces:
            self.active_traces[workflow_id]["hitl_events"].append(event)

    def complete_step(self, workflow_id: str, step: WorkflowStep, status: StepStatus, result: Any = None, error: Optional[str] = None):
        if workflow_id not in self.active_traces:
            return
        
        for s in self.active_traces[workflow_id]["steps"]:
            if s["step_id"] == step.id:
                s["status"] = status.value
                s["end_time"] = time.time()
                s["duration_sec"] = round(s["end_time"] - s["start_time"], 3)
                s["result"] = result
                s["error"] = error
                s["retries"] = step.self_healing_attempts
                break

    def finish_trace(self, workflow_id: str, overall_status: str) -> str:
        if workflow_id not in self.active_traces:
            return ""
        
        trace = self.active_traces[workflow_id]
        trace["end_time"] = time.time()
        trace["total_duration_sec"] = round(trace["end_time"] - trace["start_time"], 3)
        trace["status"] = overall_status
        
        # LLM cost is recorded at plan time (0.0 for deterministic planning)
        step_count = len(trace["steps"])
        if trace.get("cost_usd", 0.0) > 0:
            trace["cost_usd"] = round(trace["cost_usd"], 4)
        else:
            trace["cost_usd"] = 0.0
        
        # Save trace JSON
        file_name = f"trace_{workflow_id}_{int(time.time())}.json"
        file_path = os.path.join(self.log_dir, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, indent=2)
            
        return file_path

telemetry = TelemetryLogger(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "eval", "reports")))
