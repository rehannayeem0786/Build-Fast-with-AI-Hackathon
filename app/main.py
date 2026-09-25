import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from app.config import settings
from app.core.models import WorkflowDAG, HumanApprovalDecision
from app.core.planner import planner
from app.core.orchestrator import orchestrator
from app.eval.runner import benchmark_runner
from app.agents.mcp_hub import mcp_hub
from app.agents.browser_agent import browser_agent
from app.mcp.client import mcp_client
from app.mock_apps.web_portal import get_mock_portal_html


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hold ONE MCP session for the server's lifetime so state mutations
    # persist across workflows and no subprocess respawns between demos.
    await mcp_client.connect()
    yield
    await mcp_client.close()
    if browser_agent._page is not None:
        await browser_agent.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="NexusFlow AI: Autonomous Multi-App Operations & Self-Healing Browser-MCP Agent",
    lifespan=lifespan,
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Connected WebSockets for real-time telemetry streaming
active_connections: List[WebSocket] = []

async def broadcast_ws(event_payload: Dict[str, Any]):
    dead_conns = []
    for conn in active_connections:
        try:
            await conn.send_text(json.dumps(event_payload))
        except Exception:
            dead_conns.append(conn)
    for dc in dead_conns:
        if dc in active_connections:
            active_connections.remove(dc)

orchestrator.register_callback(broadcast_ws)

# Request Models
class GoalRequest(BaseModel):
    goal: str

# ----------------- UI & Sandbox Routes -----------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/portal", response_class=HTMLResponse)
async def serve_mock_portal():
    return browser_agent.dom_state

@app.post("/api/sandbox/dom-version")
async def set_dom_version(version: str = Query(..., enum=["v1", "v2"])):
    browser_agent.set_dom_version(version)
    return {"status": "SUCCESS", "current_dom_version": version}

# ----------------- WebSocket Route -----------------
@app.websocket("/ws")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle incoming client ping
            await websocket.send_text(json.dumps({"event": "PONG", "data": "alive"}))
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

# ----------------- REST API Endpoints -----------------
@app.post("/api/plan")
async def plan_workflow_endpoint(req: GoalRequest):
    dag = planner.plan_workflow(req.goal)
    orchestrator.active_workflows[dag.workflow_id] = dag
    return dag.model_dump()

@app.post("/api/execute/{workflow_id}")
async def execute_workflow_endpoint(workflow_id: str):
    if workflow_id not in orchestrator.active_workflows:
        raise HTTPException(status_code=404, detail="Workflow ID not found.")
    
    dag = orchestrator.active_workflows[workflow_id]
    
    # Run in background task to allow live streaming over WebSocket
    asyncio.create_task(orchestrator.run_workflow(dag, auto_approve_all=False))
    return {"status": "EXECUTION_DISPATCHED", "workflow_id": workflow_id}

@app.post("/api/approval/decision")
async def submit_approval_decision(decision: HumanApprovalDecision):
    success = orchestrator.submit_approval_decision(decision)
    return {"success": success, "step_id": decision.step_id, "decision": decision.decision}

@app.post("/api/workflow/{workflow_id}/undo")
async def undo_workflow(workflow_id: str):
    """Execute compensating actions to roll back reversible mutations."""
    if not mcp_client.connected:
        await mcp_client.connect()
    return await orchestrator.rollback_workflow(workflow_id)

@app.get("/api/mcp/tools")
async def list_mcp_tools():
    return {"tools": mcp_hub.list_mcp_tools()}

@app.post("/api/benchmark/run")
async def run_benchmarks_endpoint():
    summary = await benchmark_runner.run_all()
    return summary

@app.get("/api/benchmark/latest")
async def get_latest_benchmark_report():
    report_path = os.path.join(settings.LOGS_DIR, "benchmark_30_summary.json")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "No benchmark report found. Run benchmark first."}

@app.get("/api/traces")
async def list_traces():
    files = [f for f in os.listdir(settings.LOGS_DIR) if f.startswith("trace_") and f.endswith(".json")]
    return {"traces": files}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
