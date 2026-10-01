/* ================================================================
   NexusFlow AI · Dashboard Controller
   - WebSocket telemetry
   - DAG rendering with animated connectors
   - Self-healing cascade visualization
   - Benchmark matrix with filtering
   - Tab navigation
   - Trace inspector drawer
   - Animated mesh background
   - Keyboard shortcuts
   ================================================================ */

let currentWorkflowId = null;
let currentPendingStepId = null;
let currentApprovalRequest = null;
let ws = null;
let approvalTimeoutTimer = null;
let workflowMetrics = { steps: 0, healed: 0, gates: 0, startTime: null };

// ---- Preset Goals ----
const PRESETS = {
    1: "Reconcile overdue invoices in Stripe with HubSpot leads, update the tracking sheet, and queue reminder emails for approval",
    2: "Navigate to web portal, scrape hardware inventory records, enrich CRM lead LEAD-104, and submit onboarding form under mutated DOM",
    3: "Fetch top-tier qualified leads with score >= 90 from CRM, create $110,000 enterprise deal, sync to executive sheet, and dispatch contract notice"
};

function setGoal(presetId) {
    document.getElementById('goal-input').value = PRESETS[presetId] || "";
    const ta = document.getElementById('goal-input');
    ta.focus();
    ta.style.borderColor = 'var(--gold)';
    setTimeout(() => ta.style.borderColor = '', 600);
}

// ---- Tab Navigation ----
function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    document.getElementById(`tab-${tabId}`).classList.add('active');
}

// ---- WebSocket ----
function initWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        const indicator = document.getElementById('ws-indicator');
        indicator.style.borderColor = 'rgba(63, 185, 80, 0.3)';
        document.getElementById('ws-status').innerText = 'System Connected';
        appendTraceLog("WebSocket telemetry channel established.", "SUCCESS");
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerEvent(msg);
    };

    ws.onclose = () => {
        const indicator = document.getElementById('ws-indicator');
        indicator.style.borderColor = 'rgba(242, 182, 50, 0.3)';
        indicator.querySelector('.status-dot').style.background = 'var(--gold)';
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
            workflowMetrics = { steps: data.total_steps, healed: 0, gates: 0, startTime: Date.now() };
            updateMetricsStrip();
            appendTraceLog(`[DAG PLANNER] Workflow initialized with ${data.total_steps} steps · mode: ${data.planner_mode}`, "INFO", timeStr);
            break;

        case "STEP_STARTED":
            updateStepStatus(data.step_id, 'RUNNING');
            appendTraceLog(`▶ Step [${data.step_id}]: ${data.name} (${data.tool_type} · Risk: ${data.risk_level})`, "INFO", timeStr);
            break;

        case "APPROVAL_REQUIRED":
            updateStepStatus(data.step_id, 'WAITING_APPROVAL');
            workflowMetrics.gates++;
            updateMetricsStrip();
            openApprovalModal(data.request);
            appendTraceLog(`🛡️ [SAFEGUARD] Paused at ${data.step_id} — awaiting human authorization`, "WARN", timeStr);
            break;

        case "APPROVAL_GRANTED":
            updateStepStatus(data.step_id, 'RUNNING');
            appendTraceLog(`✓ [SAFEGUARD] Human ${data.decision || 'APPROVED'} for ${data.step_id}`, "SUCCESS", timeStr);
            break;

        case "APPROVAL_TIMEOUT":
            updateStepStatus(data.step_id, 'REJECTED');
            document.getElementById('approval-modal').classList.add('hidden');
            clearInterval(approvalTimeoutTimer);
            appendTraceLog(`⏱ [SAFEGUARD TIMEOUT] Fail-safe deny-by-default → ${data.step_id} REJECTED`, "ERROR", timeStr);
            break;

        case "STEP_COMPLETED":
            updateStepStatus(data.step_id, data.status);
            if (data.status === 'RECOVERED') {
                workflowMetrics.healed++;
                updateMetricsStrip();
                showHealingCascade(data);
            }
            const icon = data.status === 'RECOVERED' ? '🔄' : '✅';
            appendTraceLog(`${icon} [COMPLETED] ${data.step_id} in ${data.duration_ms}ms (${data.status})`, data.status === 'RECOVERED' ? 'WARN' : 'SUCCESS', timeStr);
            break;

        case "STEP_SKIPPED":
            updateStepStatus(data.step_id, 'SKIPPED');
            appendTraceLog(`⏭ [SKIPPED] ${data.step_id}: ${data.reason}`, "WARN", timeStr);
            break;

        case "STEP_FAILED":
            updateStepStatus(data.step_id, 'FAILED');
            appendTraceLog(`✕ [FAILED] ${data.step_id}: ${data.error}`, "ERROR", timeStr);
            break;

        case "WORKFLOW_COMPLETED": {
            const finalStatus = data.status || data.overall_status || 'COMPLETED';
            const isSuccess = finalStatus === 'COMPLETED';
            document.getElementById('workflow-status-badge').innerText = finalStatus;
            document.getElementById('workflow-status-badge').className = `badge-status ${isSuccess ? 'text-emerald' : 'text-crimson'}`;
            document.getElementById('execute-btn').disabled = false;
            showExecButton();
            const uBtn = document.getElementById('undo-btn');
            if (uBtn) uBtn.classList.remove('hidden');
            if (workflowMetrics.startTime) {
                const elapsed = ((Date.now() - workflowMetrics.startTime) / 1000).toFixed(2);
                document.getElementById('m-time').innerText = elapsed + 's';
            }
            const statusIcon = isSuccess ? '🎉' : '⚠️';
            appendTraceLog(`${statusIcon} [WORKFLOW ${finalStatus}] Trace saved · ${data.trace_path || 'reports/'}`, isSuccess ? "SUCCESS" : "WARN", timeStr);
            break;
        }

        case "WORKFLOW_UNDONE":
            document.getElementById('workflow-status-badge').innerText = data.status || 'UNDONE';
            document.getElementById('workflow-status-badge').className = 'badge-status text-gold';
            appendTraceLog(`↩️ [ROLLBACK] ${data.undone} actions compensated. Status: ${data.status}`, "SUCCESS", timeStr);
            break;
    }
}

// ---- Metrics Strip ----
function updateMetricsStrip() {
    document.getElementById('m-steps').innerText = workflowMetrics.steps || '—';
    document.getElementById('m-healed').innerText = workflowMetrics.healed || '0';
    document.getElementById('m-gates').innerText = workflowMetrics.gates || '0';
    if (workflowMetrics.startTime) {
        const elapsed = ((Date.now() - workflowMetrics.startTime) / 1000).toFixed(1);
        document.getElementById('m-time').innerText = elapsed + 's';
    }
}

// ---- Workflow Execution ----
async function startWorkflow() {
    const goal = document.getElementById('goal-input').value.trim();
    if (!goal) {
        document.getElementById('goal-input').style.borderColor = 'var(--crimson)';
        setTimeout(() => document.getElementById('goal-input').style.borderColor = '', 1000);
        return;
    }

    document.getElementById('execute-btn').disabled = true;
    showSpinner('exec-spinner');
    const undoBtn = document.getElementById('undo-btn');
    if (undoBtn) undoBtn.classList.add('hidden');
    document.getElementById('telemetry-feed').innerHTML = '';
    document.getElementById('healing-card').classList.add('hidden');
    appendTraceLog(`🧠 Planning goal: "${goal.substring(0, 80)}..."`, "INFO");

    try {
        const res = await fetch('/api/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal })
        });
        const dag = await res.json();
        currentWorkflowId = dag.workflow_id;
        document.getElementById('engine-display').innerText = dag.planner_mode === 'LLM'
            ? `LLM (${dag.planner_model || 'auto'})` : 'Heuristic Engine';
        document.getElementById('m-cost').innerText = dag.estimated_cost_usd > 0
            ? `$${dag.estimated_cost_usd.toFixed(4)}` : '$0.00';
        renderDAG(dag);

        fetch(`/api/execute/${dag.workflow_id}`, { method: 'POST' });
    } catch (err) {
        appendTraceLog(`Error starting workflow: ${err}`, "ERROR");
        document.getElementById('execute-btn').disabled = false;
        showExecButton();
    }
}

function showSpinner(id) {
    const spinner = document.getElementById(id);
    if (spinner) spinner.classList.remove('hidden');
    const btn = spinner?.closest('.btn-primary');
    if (btn) {
        const text = btn.querySelector('.btn-text');
        if (text) text.innerText = 'Processing...';
    }
}
function showExecButton() {
    const spinner = document.getElementById('exec-spinner');
    if (spinner) spinner.classList.add('hidden');
    const btn = document.getElementById('execute-btn');
    if (btn) {
        const text = btn.querySelector('.btn-text');
        if (text) text.innerText = 'Execute Goal';
    }
}

// ---- DAG Rendering ----
function renderDAG(dag) {
    const container = document.getElementById('dag-container');
    container.innerHTML = '';

    dag.steps.forEach((step, i) => {
        if (i > 0) {
            const conn = document.createElement('div');
            conn.className = 'dag-connector';
            conn.id = `dag-conn-${i}`;
            container.appendChild(conn);
        }

        const card = document.createElement('div');
        card.id = `dag-step-${step.id}`;
        card.className = `dag-step-card ${step.status}`;
        card.style.animationDelay = `${i * 0.08}s`;
        card.onclick = () => openTraceDrawer(step);

        const statusIconHTML = getStatusIcon(step.status);

        card.innerHTML = `
            <div class="step-info">
                <div class="step-header">
                    <span class="tool-badge ${step.tool_type}">${step.tool_type}</span>
                    <span class="step-title">${step.name}</span>
                </div>
                <span class="step-desc">${step.description}</span>
            </div>
            <div class="step-meta">
                <span class="step-status-icon" id="icon-${step.id}">${statusIconHTML}</span>
                <span class="badge-status" id="badge-${step.id}">${step.status}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

function getStatusIcon(status) {
    switch(status) {
        case 'SUCCESS': case 'APPROVED': return '<span class="success">✓</span>';
        case 'RUNNING': return '<span class="running">⟳</span>';
        case 'FAILED': case 'REJECTED': return '<span class="failed">✕</span>';
        case 'WAITING_APPROVAL': return '<span class="waiting">🛡️</span>';
        case 'RECOVERED': return '<span class="success">🔄</span>';
        case 'SKIPPED': return '<span class="text-muted">⏭</span>';
        default: return '<span class="text-muted">○</span>';
    }
}

function updateStepStatus(stepId, status) {
    const card = document.getElementById(`dag-step-${stepId}`);
    const badge = document.getElementById(`badge-${stepId}`);
    const icon = document.getElementById(`icon-${stepId}`);
    if (card) card.className = `dag-step-card ${status}`;
    if (badge) badge.innerText = status;
    if (icon) icon.innerHTML = getStatusIcon(status);

    // Activate connector
    const connectors = document.querySelectorAll('.dag-connector');
    connectors.forEach(c => {
        const nextCard = c.nextElementSibling;
        if (nextCard && (nextCard.classList.contains('SUCCESS') || nextCard.classList.contains('RECOVERED') || nextCard.classList.contains('APPROVED'))) {
            c.classList.add('active');
        }
    });
}

// ---- Self-Healing Cascade ----
function showHealingCascade(data) {
    const card = document.getElementById('healing-card');
    const stages = ['LEARNED_MEMORY', 'EXACT_SELECTOR', 'SEMANTIC_TEXT_GROUNDING', 'ACCESSIBILITY_TREE_GROUNDING', 'FORM_PROXIMITY_HEURISTIC'];
    // Strategy arrives nested in the step result (data.result.strategy); also accept
    // top-level healing_strategy/strategy so either payload shape works.
    const result = (data && typeof data.result === 'object' && data.result) || {};
    const hitStrategy = String(
        (data && (data.healing_strategy || data.strategy)) || result.strategy || ''
    ).toUpperCase().replace(/ /g, '_');

    // Index of the stage that actually resolved the element (-1 = unknown).
    let hitIdx = stages.findIndex(s => hitStrategy.includes(s));
    if (hitIdx === -1 && hitStrategy) hitIdx = stages.length - 1; // unknown strategy → final fallback
    // Never reveal the card without a known winning stage — a RECOVERED step is
    // still credited in the metrics strip and DAG badge either way.
    if (hitIdx === -1) return;
    card.classList.remove('hidden');

    stages.forEach((stage, i) => {
        const el = document.querySelector(`.healing-stage[data-stage="${i}"]`);
        const statusEl = document.getElementById(`hs-${i}`);
        if (!el || !statusEl) return;

        setTimeout(() => {
            el.classList.remove('hit', 'miss');
            if (i === hitIdx) {
                el.classList.add('hit');
                statusEl.innerText = '✓ HIT';
                statusEl.style.color = 'var(--emerald)';
            } else if (i < hitIdx) {
                el.classList.add('miss');
                statusEl.innerText = '✕ miss';
                statusEl.style.color = 'var(--crimson)';
            } else {
                statusEl.innerText = 'skipped';
                statusEl.style.color = 'var(--text-muted)';
            }
        }, i * 200);
    });
}

// ---- Telemetry ----
function appendTraceLog(message, level = "INFO", timeStr = null) {
    const feed = document.getElementById('telemetry-feed');
    // Remove empty state on first message
    const empty = feed.querySelector('.trace-empty-state');
    if (empty) empty.remove();

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

// ---- HITL Approval Modal ----
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

    const editArea = document.getElementById('modal-diff-after-edit');
    if (editArea) editArea.value = JSON.stringify(request.diff_after, null, 2);

    document.getElementById('approval-modal').classList.remove('hidden');

    // Animated timeout bar
    const fill = document.getElementById('timeout-fill');
    fill.style.transition = 'none';
    fill.style.width = '100%';
    requestAnimationFrame(() => {
        fill.style.transition = 'width 120s linear';
        fill.style.width = '0%';
    });
}

async function submitApproval(decision) {
    document.getElementById('approval-modal').classList.add('hidden');
    clearInterval(approvalTimeoutTimer);
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
        modified_params: modifiedParams
    };

    await fetch('/api/approval/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

// ---- Undo / Rollback ----
async function undoCurrentWorkflow() {
    if (!currentWorkflowId) return;
    appendTraceLog(`↩️ Initiating rollback for ${currentWorkflowId}...`, "INFO");
    try {
        const res = await fetch(`/api/workflow/${currentWorkflowId}/undo`, { method: 'POST' });
        const result = await res.json();
        if (result.status === 'NOTHING_TO_UNDO') {
            appendTraceLog(`No reversible actions found.`, "WARN");
        } else {
            appendTraceLog(`Rollback: ${result.undone} actions compensated.`, "SUCCESS");
            document.getElementById('workflow-status-badge').innerText = 'ROLLED_BACK';
            document.getElementById('workflow-status-badge').className = 'badge-status text-gold';
        }
    } catch (err) {
        appendTraceLog(`Rollback error: ${err}`, "ERROR");
    }
}

// ---- DOM Version ----
async function changeDomVersion() {
    const ver = document.getElementById('dom-version-select').value;
    await fetch(`/api/sandbox/dom-version?version=${ver}`, { method: 'POST' });
    document.getElementById('portal-frame').src = `/portal?t=${Date.now()}`;
    appendTraceLog(`Target Sandbox DOM → ${ver.toUpperCase()}`, "INFO");
}

// ---- Benchmark ----
async function runBenchmarks() {
    const btn = document.getElementById('bench-run-btn');
    btn.disabled = true;
    const spinner = document.getElementById('bench-spinner');
    spinner.classList.remove('hidden');
    const text = btn.querySelector('.btn-text');
    if (text) text.innerText = 'Running...';

    const log = document.getElementById('bench-log');
    log.innerHTML = '';
    appendBenchLog("Starting Benchmark-30 suite...", "INFO");

    try {
        const res = await fetch('/api/benchmark/run', { method: 'POST' });
        const data = await res.json();

        // Update stats with animation
        animateValue('b-pass-rate', data.pass_rate_pct, '%');
        animateValue('b-self-healing', data.self_healing_success_rate_pct, '%');
        document.getElementById('b-speedup').innerText = `${data.average_speedup_factor}x`;
        document.getElementById('b-cost').innerText = data.total_llm_cost_usd > 0
            ? `$${(data.total_llm_cost_usd / 30).toFixed(4)}` : '$0.00';
        document.getElementById('b-gates').innerText = data.hitl_gates_observed || '0';
        document.getElementById('b-wall-clock').innerText = data.suite_wall_clock_sec
            ? `${data.suite_wall_clock_sec}s` : '—';

        renderBenchTable(data.results || []);
        appendBenchLog(`Benchmark-30 completed! Pass: ${data.pass_rate_pct}% (${data.passed_count}/30), Speedup: ${data.average_speedup_factor}x`, "SUCCESS");
    } catch (err) {
        appendBenchLog(`Benchmark error: ${err}`, "ERROR");
    } finally {
        btn.disabled = false;
        spinner.classList.add('hidden');
        if (text) text.innerText = 'Run All 30 Tests';
    }
}

function renderBenchTable(results) {
    const wrap = document.getElementById('bench-table-wrap');
    if (!results.length) {
        wrap.innerHTML = '<div class="bench-empty">No results.</div>';
        return;
    }

    let html = `<table class="bench-table" id="bench-results-table">
        <thead><tr>
            <th>ID</th><th>Category</th><th>Task</th><th>Status</th>
            <th>Agent Time</th><th>Baseline</th><th>Speedup</th>
            <th>Self-Heal</th><th>SafeGuard</th>
        </tr></thead><tbody>`;

    results.forEach(r => {
        const statusClass = r.status === 'PASSED' ? 'pass' : 'fail';
        const statusBadge = r.status === 'PASSED' ? '✅' : '❌';
        const agentT = r.execution_time_sec < 1
            ? `${(r.execution_time_sec * 1000).toFixed(0)}ms`
            : `${r.execution_time_sec}s`;
        const sh = r.self_healing_recovered ? '🔄 Recovered' : (r.self_healing_triggered ? '⚠️ Tried' : '—');
        const hitl = r.human_approval_triggered ? '🛡️ Gated' : '—';

        html += `<tr data-category="${r.category}">
            <td>${r.test_id}</td>
            <td>${r.category}</td>
            <td>${r.task_name}</td>
            <td class="${statusClass}">${statusBadge} ${r.status}</td>
            <td>${agentT}</td>
            <td>${parseInt(r.simulated_manual_time_sec)}s</td>
            <td class="text-gold">${r.speedup_factor}x</td>
            <td>${sh}</td>
            <td>${hitl}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;
}

function filterBench(category) {
    document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
    event.target.classList.add('active');

    const rows = document.querySelectorAll('#bench-results-table tbody tr');
    rows.forEach(row => {
        if (category === 'all') {
            row.style.display = '';
        } else {
            row.style.display = row.dataset.category.includes(category) ? '' : 'none';
        }
    });
}

function appendBenchLog(msg, level) {
    const log = document.getElementById('bench-log');
    const empty = log.querySelector('.trace-empty-state');
    if (empty) empty.remove();
    const line = document.createElement('div');
    line.className = `trace-line ${level}`;
    line.innerHTML = `<span class="trace-time">[${new Date().toLocaleTimeString()}]</span><span class="trace-text">${msg}</span>`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

// ---- Trace Inspector ----
function openTraceDrawer(step) {
    const drawer = document.getElementById('trace-drawer');
    const content = document.getElementById('trace-drawer-content');
    content.innerText = JSON.stringify(step, null, 2);
    drawer.classList.remove('hidden');
}
function closeTraceDrawer() {
    document.getElementById('trace-drawer').classList.add('hidden');
}

// ---- Animated Counter ----
function animateValue(id, target, suffix = '') {
    const el = document.getElementById(id);
    const start = parseFloat(el.innerText) || 0;
    const duration = 800;
    const startTime = performance.now();

    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (target - start) * eased);
        el.innerText = current + suffix;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ---- Animated Mesh Background ----
function initMeshBackground() {
    const canvas = document.getElementById('mesh-bg');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];
    const PARTICLE_COUNT = 40;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push({
            x: Math.random() * w,
            y: Math.random() * h,
            vx: (Math.random() - 0.5) * 0.3,
            vy: (Math.random() - 0.5) * 0.3,
            r: Math.random() * 1.5 + 0.5,
        });
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0 || p.x > w) p.vx *= -1;
            if (p.y < 0 || p.y > h) p.vy *= -1;
        });

        // Connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 200) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(242, 182, 50, ${0.06 * (1 - dist / 200)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }

        // Dots
        particles.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(242, 182, 50, 0.15)';
            ctx.fill();
        });

        requestAnimationFrame(draw);
    }
    draw();
}

// ---- Keyboard Shortcuts ----
document.addEventListener('keydown', (e) => {
    // Ctrl+Enter to execute
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        startWorkflow();
    }
    // Escape to close modal / drawer
    if (e.key === 'Escape') {
        document.getElementById('approval-modal').classList.add('hidden');
        closeTraceDrawer();
    }
    // A/R/M in approval modal
    if (!document.getElementById('approval-modal').classList.contains('hidden')) {
        if (e.key === 'a' || e.key === 'A') submitApproval('APPROVE');
        if (e.key === 'r' || e.key === 'R') submitApproval('REJECT');
        if (e.key === 'm' || e.key === 'M') submitApproval('MODIFY');
    }
});

// ---- Init ----
window.onload = () => {
    initWebSocket();
    initMeshBackground();
    setGoal(1);
};
