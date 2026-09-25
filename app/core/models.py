import os
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time

class RiskLevel(str, Enum):
    LOW = "LOW"             # Read-only queries, data scraping, non-mutating searches
    MEDIUM = "MEDIUM"       # Draft generation, internal staging, temporary cache updates
    HIGH = "HIGH"           # Database modifications, sheet updates, record creations
    CRITICAL = "CRITICAL"   # Financial transactions, outbound emails, customer messaging, deletions

class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUCCESS = "SUCCESS"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class ToolType(str, Enum):
    BROWSER = "BROWSER"
    MCP_TOOL = "MCP_TOOL"
    API_CALL = "API_CALL"
    HUMAN_GATE = "HUMAN_GATE"

class WorkflowStep(BaseModel):
    id: str
    name: str
    description: str
    tool_type: ToolType
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_human_approval: bool = False
    dependencies: List[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    trace_logs: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: float = 0.0
    self_healing_attempts: int = 0
    diff_preview: Optional[Dict[str, Any]] = None

class WorkflowDAG(BaseModel):
    workflow_id: str
    goal: str
    created_at: float = Field(default_factory=time.time)
    steps: List[WorkflowStep] = Field(default_factory=list)
    overall_status: str = "INITIALIZED"
    total_steps: int = 0
    completed_steps: int = 0
    total_duration_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    planner_mode: str = "HEURISTIC"   # LLM | HEURISTIC
    planner_model: Optional[str] = None

class HumanApprovalRequest(BaseModel):
    workflow_id: str
    step_id: str
    action_type: str
    risk_level: RiskLevel
    title: str
    description: str
    diff_before: Dict[str, Any]
    diff_after: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)

class HumanApprovalDecision(BaseModel):
    workflow_id: str
    step_id: str
    decision: str  # "APPROVE" or "REJECT" or "MODIFY"
    modified_params: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None

class BenchmarkResult(BaseModel):
    test_id: str
    category: str
    task_name: str
    goal: str
    status: str
    steps_total: int
    steps_passed: int
    self_healing_triggered: bool
    self_healing_recovered: bool
    human_approval_triggered: bool
    execution_time_sec: float
    simulated_manual_time_sec: float
    speedup_factor: float
    cost_usd: float
    trace_log_path: str
    notes: str = ""   # failed contract checks, empty when all pass
