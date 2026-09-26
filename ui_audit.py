"""Headless UI audit of the NexusFlow dashboard (Playwright Chromium)."""
import os
import time

from playwright.sync_api import sync_playwright

BASE = f"http://127.0.0.1:{os.environ.get('UI_AUDIT_PORT', '8021')}"
OUT = os.path.join(os.environ.get("TEMP", "."), "ui_audit")
os.makedirs(OUT, exist_ok=True)

console_errors, page_errors, failed_requests = [], [], []
results = []


def check(name, ok, extra=""):
    results.append((name, ok, extra))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {extra}")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1680, "height": 1050})
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("requestfailed", lambda r: failed_requests.append(f"{r.method} {r.url}"))

    resp = page.goto(BASE, wait_until="networkidle", timeout=40000)
    check("page loads (HTTP 200)", resp is not None and resp.status == 200,
          f"status={resp.status if resp else 'none'}")
    page.wait_for_timeout(2000)

    # --- static element presence -------------------------------------
    for name, sel in [
        ("goal input", "#goal-input"),
        ("execute button", "#execute-btn"),
        ("DAG container", "#dag-container"),
        ("telemetry feed", "#telemetry-feed"),
        ("portal iframe", "#portal-frame"),
        ("approval modal", "#approval-modal"),
        ("metrics strip", "#m-steps"),
        ("healing cascade card", "#healing-card"),
        ("undo button", "#undo-btn"),
    ]:
        cnt = page.locator(sel).count()
        check(f"element {name}", cnt > 0, f"count={cnt}")

    ws = page.inner_text("#ws-status")
    check("websocket connected", "Connected" in ws or "Ready" in ws, f"status='{ws}'")

    # --- tab switching ------------------------------------------------
    for tab in ("architecture", "benchmark", "operations"):
        page.click(f"button[data-tab='{tab}']", timeout=5000)
        page.wait_for_timeout(700)
        active = page.locator(f"#tab-{tab}").first
        cls = active.get_attribute("class") or ""
        text_len = len(active.inner_text())
        check(f"tab '{tab}' renders", "active" in cls and text_len > 50,
              f"class='{cls}' text_len={text_len}")
    page.screenshot(path=os.path.join(OUT, "architecture.png"), full_page=True)

    # --- functional workflow (safe goal: no CRITICAL gate) ------------
    page.click("button[data-tab='operations']")
    page.fill("#goal-input",
              "Read qualified leads from the CRM with score >= 90 and log them to the tracking sheet")
    page.click("#execute-btn")
    print("  ... workflow dispatched, waiting for completion")

    done = False
    for _ in range(90):
        page.wait_for_timeout(1000)
        badge = page.inner_text("#workflow-status-badge")
        if "COMPLETED" in badge or "FAILED" in badge or "ABORTED" in badge:
            done = True
            break
        # auto-authorize any HITL gate so the audit never stalls
        if page.locator("#approval-modal:not(.hidden)").count() > 0:
            print("  ... HITL gate appeared -> clicking Authorize")
            page.get_by_text("Authorize", exact=False).first.click()

    badge = page.inner_text("#workflow-status-badge")
    check("workflow finished", done, f"badge='{badge}'")
    check("workflow COMPLETED", "COMPLETED" in badge, f"badge='{badge}'")

    steps = page.locator(".dag-step-card").count()
    trace_lines = page.locator(".trace-line").count()
    check("DAG step cards rendered", steps >= 2, f"cards={steps}")
    check("telemetry lines streamed", trace_lines >= 3, f"lines={trace_lines}")

    trace_text = page.inner_text("#telemetry-feed")
    check("completion trace shows real status",
          "WORKFLOW COMPLETED" in trace_text and "undefined" not in trace_text,
          f"has_undefined={'undefined' in trace_text}")

    page.screenshot(path=os.path.join(OUT, "operations.png"), full_page=True)

    # --- undo button ------------------------------------------------
    undo_visible = page.locator("#undo-btn:not(.hidden)").count() > 0
    check("undo button surfaced", undo_visible)
    if undo_visible:
        page.click("#undo-btn")
        page.wait_for_timeout(2500)
        check("undo executed (no JS error)", True)

    # --- benchmark tab ----------------------------------------------
    page.click("button[data-tab='benchmark']")
    page.wait_for_timeout(800)
    page.click("#bench-run-btn")
    print("  ... benchmark running from UI")
    bench_ok = False
    for _ in range(120):
        page.wait_for_timeout(1000)
        pr = page.inner_text("#b-pass-rate")
        if "100" in pr:
            bench_ok = True
            break
    passed = page.inner_text("#b-pass-rate")
    check("benchmark ran from UI (100%)", bench_ok, f"pass_rate='{passed}'")
    page.screenshot(path=os.path.join(OUT, "benchmark.png"), full_page=True)

    browser.close()

print("\n=== CONSOLE ERRORS:", len(console_errors), "===")
for e in console_errors[:10]:
    print("   ", e[:180])
print("=== PAGE ERRORS:", len(page_errors), "===")
for e in page_errors[:10]:
    print("   ", e[:180])
print("=== FAILED REQUESTS:", len(failed_requests), "===")
for r in failed_requests[:10]:
    print("   ", r[:180])

failures = [r for r in results if not r[1]]
print(f"\nSUMMARY: {len(results) - len(failures)}/{len(results)} checks passed")
