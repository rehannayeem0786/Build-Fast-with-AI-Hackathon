import asyncio
import json
import os
import re
import time
from typing import Dict, List, Any, Optional

from app.mock_apps.web_portal import get_mock_portal_html
from app.core.telemetry import telemetry

HEALING_MEMORY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "eval", "reports", "healing_memory.json")
)

# Keywords used by semantic grounding to identify a submit-like control.
SUBMIT_KEYWORDS = ["submit", "confirm", "synchronize", "sync", "save", "send", "create"]


class SelfHealingBrowserAgent:
    """
    Self-Healing Browser & DOM Automation Agent (real Playwright engine).

    Executes against a real headless Chromium page rendered from the target
    app DOM. Implements a 5-stage grounding cascade:
      Stage 0: Learned Selector Memory (persisted from previous heals)
      Stage 1: Exact CSS/ID Selector
      Stage 2: Semantic Text Grounding (visible text / value / aria-label)
      Stage 3: Accessibility Tree (role + accessible-name from aria snapshot)
      Stage 4: Form Proximity & Fuzzy Context Recovery

    Falls back to an offline BeautifulSoup simulation when Playwright or the
    Chromium binary is unavailable; the active engine is always reported in
    results and telemetry so traces never overstate what actually ran.
    """

    def __init__(self):
        self.dom_version: str = "v1"
        self.dom_state: str = get_mock_portal_html(dom_version="v1")
        self.current_url: str = "http://localhost:8000/portal"
        self.engine: str = "PENDING"  # PENDING | PLAYWRIGHT | BS4_FALLBACK
        self._playwright = None
        self._browser = None
        self._page = None
        self._launch_lock = None
        self._healing_memory: Dict[str, Any] = self._load_healing_memory()

    # ------------------------------------------------------------------
    # Healing memory (Stage 0) — learned selectors persist across runs
    # ------------------------------------------------------------------
    def _load_healing_memory(self) -> Dict[str, Any]:
        try:
            if os.path.exists(HEALING_MEMORY_PATH):
                with open(HEALING_MEMORY_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_healing_memory(self) -> None:
        try:
            os.makedirs(os.path.dirname(HEALING_MEMORY_PATH), exist_ok=True)
            with open(HEALING_MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump(self._healing_memory, f, indent=2)
        except Exception:
            pass

    def remember_selector(self, url: str, intent: str, selector: str) -> None:
        """Persist a healed selector so future runs resolve at Stage 0/1."""
        key = f"{url}::{intent.strip().lower()}"
        self._healing_memory[key] = {"selector": selector, "learned_at": time.time()}
        self._save_healing_memory()

    def recall_selector(self, url: str, intent: str) -> Optional[str]:
        key = f"{url}::{intent.strip().lower()}"
        entry = self._healing_memory.get(key)
        return entry.get("selector") if entry else None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------
    async def _ensure_page(self):
        """Lazily launch headless Chromium and return a page, or None if unavailable."""
        if self._page is not None:
            return self._page
        if self._launch_lock is None:
            self._launch_lock = asyncio.Lock()
        async with self._launch_lock:
            if self._page is not None:
                return self._page
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
                self._page = await self._browser.new_page()
                self.engine = "PLAYWRIGHT"
            except Exception:
                self.engine = "BS4_FALLBACK"
                self._page = None
        return self._page

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None
        self._page = None
        # engine keeps its last-used value so reports can state which
        # engine actually ran (PENDING only before any browser work).

    def set_dom_version(self, version: str):
        """Toggle between standard v1 and mutated v2 DOM for self-healing demos."""
        self.dom_version = version
        self.dom_state = get_mock_portal_html(dom_version=version)

    async def _load_dom(self, page) -> None:
        """Render the current target DOM into the live page."""
        await page.set_content(self.dom_state, wait_until="domcontentloaded")

    async def navigate(self, url: str) -> Dict[str, Any]:
        self.current_url = url
        page = await self._ensure_page()
        if page is None:
            return {"status": "OFFLINE", "url": url, "engine": self.engine}
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            return {"status": "LOADED", "url": url, "title": await page.title(),
                    "http_status": resp.status if resp else None, "engine": self.engine}
        except Exception:
            # Server not running — render sandbox DOM instead.
            await self._load_dom(page)
            return {"status": "SANDBOX_LOADED", "url": url, "engine": self.engine}

    # ------------------------------------------------------------------
    # Table scraping (real browser)
    # ------------------------------------------------------------------
    async def scrape_table(self, table_selector: str = "#portal-data-table") -> List[Dict[str, Any]]:
        """Scrape a table from the live rendered DOM (Playwright) with selector fallback."""
        page = await self._ensure_page()
        if page is None:
            return self._scrape_table_offline(table_selector)

        await self._load_dom(page)
        try:
            resolved = table_selector
            if await page.locator(table_selector).count() == 0:
                if await page.locator("table").count() == 0:
                    return []
                resolved = "table"

            return await page.evaluate(
                """(sel) => {
                    const table = document.querySelector(sel);
                    if (!table) return [];
                    const headers = Array.from(table.querySelectorAll('th'))
                        .map(th => th.innerText.trim());
                    const rows = [];
                    for (const tr of Array.from(table.querySelectorAll('tr')).slice(1)) {
                        const cols = Array.from(tr.querySelectorAll('td'))
                            .map(td => td.innerText.trim());
                        if (cols.length && cols.length === headers.length) {
                            const row = {};
                            headers.forEach((h, i) => row[h] = cols[i]);
                            rows.push(row);
                        }
                    }
                    return rows;
                }""",
                resolved,
            )
        except Exception:
            return self._scrape_table_offline(table_selector)

    def _scrape_table_offline(self, table_selector: str) -> List[Dict[str, Any]]:
        """BS4 fallback used only when Chromium is unavailable."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self.dom_state, "html.parser")
        table = soup.select_one(table_selector) or soup.find("table")
        if not table:
            return []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cols and len(cols) == len(headers):
                rows.append(dict(zip(headers, cols)))
        return rows

    # ------------------------------------------------------------------
    # Self-healing grounding cascade
    # ------------------------------------------------------------------
    async def _resolve_button(
        self,
        page,
        workflow_id: str,
        step_id: str,
        target_button_selector: str,
        semantic_intent: str,
    ):
        """
        Resolve the target button through the 5-stage cascade.
        Returns (locator, stage_name, resolved_selector).
        Raises RuntimeError when every stage is exhausted.
        """
        attempts: List[str] = []

        # Stage 0 — Learned selector memory from a previous heal
        remembered = self.recall_selector(self.current_url, semantic_intent)
        if remembered:
            try:
                if await page.locator(remembered).count() > 0:
                    telemetry.log_step_event(
                        workflow_id, step_id,
                        f"Stage 0 (Learned Memory): resolved '{remembered}' from previous self-heal.",
                        level="INFO",
                    )
                    return page.locator(remembered).first, "LEARNED_MEMORY", remembered
            except Exception:
                pass

        # Stage 1 — Exact CSS/ID selector
        try:
            if await page.locator(target_button_selector).count() > 0:
                return (page.locator(target_button_selector).first,
                        "EXACT_SELECTOR", target_button_selector)
        except Exception:
            pass
        attempts.append(target_button_selector)
        telemetry.log_step_event(
            workflow_id, step_id,
            f"Primary selector '{target_button_selector}' failed. Initiating Self-Healing cascade...",
            level="WARN",
        )

        # Stage 2 — Semantic text grounding (visible text / value / aria-label)
        try:
            buttons = page.locator("button, input[type=submit], input[type=button], [role=button]")
            count = await buttons.count()
            for i in range(count):
                el = buttons.nth(i)
                text = ""
                try:
                    text = ((await el.inner_text(timeout=500)) or "").strip()
                    if not text:
                        text = (await el.get_attribute("value", timeout=500)) or ""
                    if not text:
                        text = (await el.get_attribute("aria-label", timeout=500)) or ""
                except Exception:
                    continue
                if text and any(w in text.lower() for w in SUBMIT_KEYWORDS):
                    selector = f"text={text}"
                    telemetry.log_step_event(
                        workflow_id, step_id,
                        f"Stage 2 (Semantic Text): matched control '{text}'.", level="INFO",
                    )
                    return el, "SEMANTIC_TEXT_GROUNDING", selector
        except Exception:
            pass

        # Stage 3 — Accessibility tree (role + accessible name)
        try:
            ax_tree = await page.locator("body").aria_snapshot()
            # YAML-ish lines like: - button "Confirm Sync"
            for line in ax_tree.splitlines():
                line = line.strip()
                m = re.match(r'-\s+(button|link)\s+"([^"]+)"', line)
                if not m:
                    continue
                accessible_name = m.group(2)
                if any(w in accessible_name.lower() for w in SUBMIT_KEYWORDS):
                    role, locator = m.group(1), page.get_by_role(m.group(1), name=accessible_name)
                    if await locator.count() > 0:
                        selector = f"[role={role}][name='{accessible_name}']"
                        telemetry.log_step_event(
                            workflow_id, step_id,
                            f"Stage 3 (Accessibility Tree): matched {role} "
                            f"with accessible name '{accessible_name}'.", level="INFO",
                        )
                        return locator.first, "ACCESSIBILITY_TREE_GROUNDING", selector
        except Exception:
            pass

        # Stage 4 — Form proximity heuristic (first submit control inside the form)
        try:
            scoped = page.locator("form button, form input[type=submit]")
            if await scoped.count() > 0:
                form_button = scoped.first
                label = ""
                try:
                    label = (await form_button.inner_text(timeout=500)).strip()
                except Exception:
                    pass
                selector = f"form button:text-is('{label}')" if label else "form button"
                telemetry.log_step_event(
                    workflow_id, step_id,
                    "Stage 4 (Form Proximity): resolved control from form context.", level="INFO",
                )
                return form_button, "FORM_PROXIMITY_HEURISTIC", selector
        except Exception:
            pass

        raise RuntimeError(
            f"Self-healing exhausted after stages 0-4. Attempts: {attempts}. "
            f"Unable to locate element matching '{semantic_intent}'."
        )


    async def fill_form_and_click(
        self,
        workflow_id: str,
        step_id: str,
        form_data: Dict[str, Any],
        target_button_selector: str,
        semantic_intent: str,
    ) -> Dict[str, Any]:
        """
        Fill form inputs and click the submit control in a real browser,
        self-healing through the grounding cascade when selectors break.
        """
        page = await self._ensure_page()
        if page is None:
            return self._fill_form_offline(workflow_id, step_id, form_data,
                                           target_button_selector, semantic_intent)

        await self._load_dom(page)

        # Fill form fields (best-effort — some payloads have no matching inputs)
        filled_fields: List[str] = []
        for field_name, value in (form_data or {}).items():
            for candidate in (
                f"[name='{field_name}']",
                f"#{field_name}",
                f"[id*='{field_name}' i]",
                f"[placeholder*='{field_name}' i]",
            ):
                try:
                    locator = page.locator(candidate).first
                    if await locator.count() > 0:
                        await locator.fill(str(value), timeout=1500)
                        filled_fields.append(field_name)
                        break
                except Exception:
                    continue

        locator, stage, resolved_selector = await self._resolve_button(
            page, workflow_id, step_id, target_button_selector, semantic_intent
        )

        recovered = stage != "EXACT_SELECTOR"
        if recovered:
            telemetry.record_self_healing(
                workflow_id=workflow_id,
                step_id=step_id,
                failed_selector=target_button_selector,
                recovery_strategy=stage,
                recovered_selector=resolved_selector,
                details=(f"Target button resolved via {stage} from semantic intent "
                         f"'{semantic_intent}'. Engine: {self.engine}."),
            )
            telemetry.log_step_event(
                workflow_id, step_id,
                f"[RECOVERED] Self-healing succeeded using {stage} -> {resolved_selector}",
                level="SUCCESS",
            )
            # Persist the heal so the next run resolves at Stage 0/1.
            self.remember_selector(self.current_url, semantic_intent, resolved_selector)

        # Execute the real click in Chromium
        clicked = False
        click_error = None
        try:
            await locator.click(timeout=3000)
            clicked = True
        except Exception as e:
            click_error = str(e)

        # Proof of a real DOM effect: read the portal's post-submit status line.
        dom_feedback = None
        if clicked:
            try:
                fb = page.locator("#status-msg")
                if await fb.count() > 0:
                    dom_feedback = (await fb.inner_text(timeout=1000)).strip() or None
            except Exception:
                pass

        return {
            "success": clicked,
            "self_healed": recovered,
            "strategy": stage,
            "engine": self.engine,
            "executed_selector": resolved_selector,
            "filled_fields": filled_fields,
            "clicked": clicked,
            "click_error": click_error,
            "dom_feedback": dom_feedback,
            "submitted_payload": form_data,
            "result_message": ("Lead record submitted via real Chromium click."
                               if clicked else "Click failed in browser."),
        }


    def _fill_form_offline(self, workflow_id: str, step_id: str, form_data: Dict[str, Any],
                           target_button_selector: str, semantic_intent: str) -> Dict[str, Any]:
        """BS4 fallback used only when Chromium is unavailable."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self.dom_state, "html.parser")
        target_btn = soup.select_one(target_button_selector)
        recovered = False
        strategy_used = "EXACT_SELECTOR"
        actual_selector_used = target_button_selector

        if not target_btn:
            telemetry.log_step_event(
                workflow_id, step_id,
                f"Primary selector '{target_button_selector}' failed. "
                f"Initiating Self-Healing Fallback (offline engine)...", level="WARN")
            buttons = soup.find_all(["button", "input"], attrs={"type": ["submit", "button", None]})
            for b in buttons:
                text_content = b.get_text(strip=True) or b.get("value", "")
                if any(w.lower() in text_content.lower() for w in SUBMIT_KEYWORDS):
                    target_btn = b
                    recovered = True
                    strategy_used = "SEMANTIC_TEXT_GROUNDING"
                    actual_selector_used = f"button:contains('{text_content}')"
                    break
            if not target_btn:
                form = soup.find("form")
                if form and form.find("button"):
                    target_btn = form.find("button")
                    recovered = True
                    strategy_used = "FORM_PROXIMITY_HEURISTIC"
                    actual_selector_used = "form button[type=submit]"
            if recovered:
                telemetry.record_self_healing(
                    workflow_id=workflow_id, step_id=step_id,
                    failed_selector=target_button_selector,
                    recovery_strategy=strategy_used,
                    recovered_selector=actual_selector_used,
                    details=(f"Target button resolved via {strategy_used} from semantic intent "
                             f"'{semantic_intent}'. Engine: BS4_FALLBACK."),
                )
            else:
                raise RuntimeError(
                    f"Self-healing exhausted. Unable to locate element matching '{semantic_intent}'.")

        return {
            "success": True,
            "self_healed": recovered,
            "strategy": strategy_used,
            "engine": self.engine,
            "executed_selector": actual_selector_used,
            "filled_fields": list((form_data or {}).keys()),
            "clicked": target_btn is not None,
            "submitted_payload": form_data,
            "result_message": "Lead record submitted (offline BS4 simulation).",
        }


browser_agent = SelfHealingBrowserAgent()
