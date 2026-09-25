import time
from typing import Dict, Any, Tuple
from app.core.models import RiskLevel, WorkflowStep, HumanApprovalRequest, ToolType

class SafeGuardEngine:
    """
    SafeGuard Risk Gate:
    Enforces Human-in-the-Loop (HITL) policies.
    - LOW: Read-only operations, queries, web scraping -> Autonomous Execution
    - MEDIUM: Staging data, generating drafts, local caching -> Autonomous with Audit Log
    - HIGH: Database mutation, updating sheets, modifying customer status -> Configurable Gate
    - CRITICAL: Financial charges, sending external emails/messages, deleting records -> MANDATORY Human Gate
    """
    
    CRITICAL_TOOLS = ["charge", "charge_invoice", "send_external_email", "email_send_reminder", "email", "delete", "refund"]
    HIGH_RISK_TOOLS = ["update_lead", "create_deal", "append_sheet_row", "update_sheet_row", "sheets_append_row", "sheets_update_row", "fill_form_and_click", "submit_web_form"]
    
    def assess_risk(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[RiskLevel, bool]:
        """
        Returns (RiskLevel, requires_human_approval)
        """
        tool_lower = tool_name.lower()
        
        # Check critical
        for ct in self.CRITICAL_TOOLS:
            if ct in tool_lower:
                return (RiskLevel.CRITICAL, True)
                
        # Check high
        for ht in self.HIGH_RISK_TOOLS:
            if ht in tool_lower:
                return (RiskLevel.HIGH, False) # Can be auto or semi-gated
                
        if "get" in tool_lower or "list" in tool_lower or "read" in tool_lower or "scrape" in tool_lower:
            return (RiskLevel.LOW, False)
            
        return (RiskLevel.MEDIUM, False)

    def generate_approval_request(self, workflow_id: str, step: WorkflowStep, current_system_state: Dict[str, Any]) -> HumanApprovalRequest:
        """
        Constructs a rich diff preview for the human reviewer.
        """
        tool_name = step.tool_name
        params = step.parameters
        
        diff_before = {}
        diff_after = {}
        title = f"Approval Required: {step.name}"
        desc = f"Action '{tool_name}' carries {step.risk_level.value} operational risk."
        
        if "charge" in tool_name:
            invoice_id = params.get("invoice_id", "UNKNOWN")
            amount = params.get("amount", "N/A")
            diff_before = {"invoice_id": invoice_id, "status": "OVERDUE", "payment_action": "PENDING"}
            diff_after = {"invoice_id": invoice_id, "status": "PAID", "charge_amount": amount, "method": "card_auto"}
            desc = f"Authorizing automatic payment charge for invoice {invoice_id}."
            
        elif "email" in tool_name or "reminder" in tool_name:
            to_email = params.get("to_email", "client@domain.com")
            subject = params.get("subject", "Automated Notice")
            diff_before = {"recipient": to_email, "outbox_status": "DRAFT_QUEUED"}
            diff_after = {"recipient": to_email, "subject": subject, "outbox_status": "DISPATCHED_TO_SMTP"}
            desc = f"Dispatching outbound email message to {to_email}."
            
        elif "update_lead" in tool_name:
            lead_id = params.get("lead_id", "LEAD-101")
            diff_before = current_system_state.get(lead_id, {"status": "OLD_STATE"})
            diff_after = {**diff_before, **params.get("updates", {})}
            desc = f"Updating CRM Lead {lead_id} properties."
            
        else:
            diff_before = {"state": "PRE_EXECUTION"}
            diff_after = {"state": "POST_EXECUTION", "intended_params": params}
            
        return HumanApprovalRequest(
            workflow_id=workflow_id,
            step_id=step.id,
            action_type=tool_name,
            risk_level=step.risk_level,
            title=title,
            description=desc,
            diff_before=diff_before,
            diff_after=diff_after,
            timestamp=time.time()
        )

safeguard = SafeGuardEngine()
