let currentWorkflowId = null;
let currentPendingStepId = null;
let currentApprovalRequest = null;
let ws = null;

// Preset Goals
const PRESETS = {
    1: "Reconcile overdue invoices in Stripe with HubSpot leads, update the tracking sheet, and queue reminder emails for approval",
    2: "Navigate to web portal, scrape hardware inventory records, enrich CRM lead LEAD-104, and submit onboarding form under mutated DOM",
    3: "Fetch top-tier qualified leads with score >= 90 from CRM, create $110,000 enterprise deal, sync to executive sheet, and dispatch contract notice"
};

function setGoal(presetId) {
    document.getElementById('goal-input').value = PRESETS[presetId] || "";
}

function initWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        document.getElementById('ws-status').innerText = 'System Connected';
        appendTraceLog("WebSocket telemetry channel established.", "SUCCESS");
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerEvent(msg);
    };

    ws.onclose = () => {
        document.getElementById('ws-status').innerText = 'Reconnecting...';
        setTimeout(initWebSocket, 2000);
    };
}

function handleServerEvent(payload) {
    const { event, timestamp, data } = payload;
    const timeStr = new Date(timestamp * 1000).toLocaleTimeString();

    switch(event) {
        case "WORKFLOW_STARTED":
            document.getElementById('workflow-status-badge').innerText = 'RUNNING';
            document.getElementById('workflow-status-badge').className = 'badge-status text-gold';
            document.getElementById('active-trace-id').innerText = `Trace: ${data.workflow_id}`;
            const undoBtn = document.getElementById('undo-btn');
            if (undoBtn) undoBtn.classList.add('hidden');
            appendTraceLog(`[DAG PLANNER] Workflow initialized with ${data.total_steps} execution steps. (${data.planner_mode})`, "INFO", timeStr);
            break;

        case "STEP_STARTED":
            updateStepStatus(data.step_id, 'RUNNING');
            appendTraceLog(`Executing Step [${data.step_id}]: ${data.name} (${data.tool_type} · Risk: ${data.risk_level})`, "INFO", timeStr);
            break;

        case "APPROVAL_REQUIRED":
            updateStepStatus(data.step_id, 'WAITING_APPROVAL');
            openApprovalModal(data.request);
            appendTraceLog(`[SAFEGUARD GATE] Paused at step ${data.step_id}. Awaiting human authorization...`, "WARN", timeStr);
            break;

        case "APPROVAL_GRANTED":
            updateStepStatus(data.step_id, 'RUNNING');
            appendTraceLog(`[SAFEGUARD] Human approval (${data.decision || 'GRANTED'}) for step ${data.step_id}. Resuming execution...`, "SUCCESS", timeStr);
            break;

        case "APPROVAL_TIMEOUT":
            updateStepStatus(data.step_id, 'REJECTED');
            document.getElementById('approval-modal').classList.add('hidden');
            appendTraceLog(`[SAFEGUARD TIMEOUT] Fail-safe deny-by-default triggered for step ${data.step_id}. Action REJECTED.`, "ERROR", timeStr);
            break;

        case "STEP_COMPLETED":
            updateStepStatus(data.step_id, data.status);
            appendTraceLog(`[STEP COMPLETED] ${data.step_id} finished in ${data.duration_ms}ms (Status: ${data.status})`, data.status === 'RECOVERED' ? 'WARN' : 'SUCCESS', timeStr);
            break;

        case "STEP_SKIPPED":
            updateStepStatus(data.step_id, 'SKIPPED');
            appendTraceLog(`[STEP SKIPPED] ${data.step_id}: ${data.reason}`, "WARN", timeStr);
            break;

        case "STEP_FAILED":
            updateStepStatus(data.step_id, 'FAILED');
            appendTraceLog(`[STEP FAILED] ${data.step_id}: ${data.error}`, "ERROR", timeStr);
            break;

        case "WORKFLOW_COMPLETED":
            const isSuccess = data.overall_status === 'COMPLETED';
            document.getElementById('workflow-status-badge').innerText = data.overall_status || 'COMPLETED';
            document.getElementById('workflow-status-badge').className = `badge-status ${isSuccess ? 'text-emerald' : 'text-crimson'}`;
            document.getElementById('execute-btn').disabled = false;
            const uBtn = document.getElementById('undo-btn');
            if (uBtn) uBtn.classList.remove('hidden');
            appendTraceLog(`[WORKFLOW FINISHED] Status: ${data.overall_status}. Trace saved to ${data.trace_path || 'reports/'}`, isSuccess ? "SUCCESS" : "WARN", timeStr);
            break;

        case "WORKFLOW_UNDONE":
            document.getElementById('workflow-status-badge').innerText = data.status || 'UNDONE';
            document.getElementById('workflow-status-badge').className = 'badge-status text-gold';
            appendTraceLog(`[ROLLBACK COMPENSATED] ${data.undone} actions rolled back. Status: ${data.status}`, "SUCCESS", timeStr);
            break;
    }
}

async function startWorkflow() {
    const goal = document.getElementById('goal-input').value.trim();
    if (!goal) {
        alert("Please enter an operational goal.");
        return;
    }

    document.getElementById('execute-btn').disabled = true;
    const undoBtn = document.getElementById('undo-btn');
    if (undoBtn) undoBtn.classList.add('hidden');
    document.getElementById('telemetry-feed').innerHTML = '';
    appendTraceLog(`Planning goal: "${goal}"...`, "INFO");

    try {
        const res = await fetch('/api/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal })
        });
        const dag = await res.json();
        currentWorkflowId = dag.workflow_id;
        renderDAG(dag);

        // Run workflow
        fetch(`/api/execute/${dag.workflow_id}`, { method: 'POST' });

    } catch (err) {
        appendTraceLog(`Error starting workflow: ${err}`, "ERROR");
        document.getElementById('execute-btn').disabled = false;
    }
}

function renderDAG(dag) {
    const container = document.getElementById('dag-container');
    container.innerHTML = '';

    dag.steps.forEach(step => {
        const card = document.createElement('div');
        card.id = `dag-step-${step.id}`;
        card.className = `dag-step-card ${step.status}`;

        card.innerHTML = `
            <div class="step-info">
                <div class="step-header">
                    <span class="tool-badge ${step.tool_type}">${step.tool_type}</span>
                    <span class="step-title">${step.name}</span>
                </div>
                <span class="step-desc">${step.description}</span>
            </div>
            <div class="step-meta">
                <span class="badge-status" id="badge-${step.id}">${step.status}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

function updateStepStatus(stepId, status) {
    const card = document.getElementById(`dag-step-${stepId}`);
    const badge = document.getElementById(`badge-${stepId}`);
    if (card) {
        card.className = `dag-step-card ${status}`;
    }
    if (badge) {
        badge.innerText = status;
    }
}

function appendTraceLog(message, level = "INFO", timeStr = null) {
    const feed = document.getElementById('telemetry-feed');
    const line = document.createElement('div');
    line.className = `trace-line ${level}`;
    const t = timeStr || new Date().toLocaleTimeString();

    line.innerHTML = `
        <span class="trace-time">[${t}] · ${level}</span>
        <span class="trace-text">${message}</span>
    `;
    feed.appendChild(line);
    feed.scrollTop = feed.scrollHeight;
}

function toggleModifySection() {
    const wrap = document.getElementById('modify-editor-wrap');
    const icon = document.getElementById('modify-toggle-icon');
    if (wrap.classList.contains('hidden')) {
        wrap.classList.remove('hidden');
        icon.innerText = '▼';
    } else {
        wrap.classList.add('hidden');
        icon.innerText = '▶';
    }
}

function openApprovalModal(request) {
    currentPendingStepId = request.step_id;
    currentApprovalRequest = request;
    document.getElementById('modal-title').innerText = request.title;
    document.getElementById('modal-desc').innerText = request.description;
    document.getElementById('modal-risk-badge').innerText = `RISK: ${request.risk_level}`;
    document.getElementById('modal-diff-before').innerText = JSON.stringify(request.diff_before, null, 2);
    document.getElementById('modal-diff-after').innerText = JSON.stringify(request.diff_after, null, 2);
    
    // Populate editable override payload
    const editArea = document.getElementById('modal-diff-after-edit');
    if (editArea) {
        editArea.value = JSON.stringify(request.diff_after, null, 2);
    }
    document.getElementById('approval-modal').classList.remove('hidden');
}

async function submitApproval(decision) {
    document.getElementById('approval-modal').classList.add('hidden');
    if (!currentWorkflowId || !currentPendingStepId) return;

    let modifiedParams = null;
    if (decision === 'MODIFY') {
        const editArea = document.getElementById('modal-diff-after-edit');
        if (editArea && editArea.value) {
            try {
                modifiedParams = JSON.parse(editArea.value);
            } catch (e) {
                alert("Invalid JSON in parameter override field.");
                return;
            }
        }
    }

    const payload = {
        workflow_id: currentWorkflowId,
        step_id: currentPendingStepId,
        decision: decision,
        modified_parameters: modifiedParams
    };

    await fetch('/api/approval/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

async function undoCurrentWorkflow() {
    if (!currentWorkflowId) return;
    appendTraceLog(`Initiating rollback for workflow ${currentWorkflowId}...`, "INFO");
    try {
        const res = await fetch(`/api/workflow/${currentWorkflowId}/undo`, { method: 'POST' });
        const result = await res.json();
        if (result.status === 'NOTHING_TO_UNDO') {
            appendTraceLog(`No reversible compensating actions found for ${currentWorkflowId}.`, "WARN");
        } else {
            appendTraceLog(`Rollback completed: ${result.undone} actions compensated successfully.`, "SUCCESS");
            document.getElementById('workflow-status-badge').innerText = 'ROLLED_BACK';
            document.getElementById('workflow-status-badge').className = 'badge-status text-gold';
        }
    } catch (err) {
        appendTraceLog(`Error during rollback: ${err}`, "ERROR");
    }
}

async function changeDomVersion() {
    const ver = document.getElementById('dom-version-select').value;
    await fetch(`/api/sandbox/dom-version?version=${ver}`, { method: 'POST' });
    document.getElementById('portal-frame').src = `/portal?t=${Date.now()}`;
    appendTraceLog(`Target Sandbox DOM updated to: ${ver.toUpperCase()}`, "INFO");
}

async function runBenchmarks() {
    appendTraceLog("Starting Benchmark-30 suite execution...", "INFO");
    const res = await fetch('/api/benchmark/run', { method: 'POST' });
    const data = await res.json();
    document.getElementById('b-pass-rate').innerText = `${data.pass_rate_pct}%`;
    document.getElementById('b-self-healing').innerText = `${data.self_healing_success_rate_pct}%`;
    document.getElementById('b-speedup').innerText = `${data.average_speedup_factor}x`;
    document.getElementById('b-cost').innerText = `$${(data.total_llm_cost_usd / 30).toFixed(2)}`;
    appendTraceLog(`Benchmark-30 completed! Pass rate: ${data.pass_rate_pct}% (${data.passed_count}/30), Speedup: ${data.average_speedup_factor}x`, "SUCCESS");
}

window.onload = () => {
    initWebSocket();
    setGoal(1);
};
