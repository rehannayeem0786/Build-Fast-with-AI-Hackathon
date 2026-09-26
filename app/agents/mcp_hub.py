import json
import time
from typing import Dict, List, Any, Optional
from app.mock_apps.crm_server import mock_crm
from app.mock_apps.billing_server import mock_billing
from app.mock_apps.sheets_server import mock_sheets

class MCPToolHub:
    """
    Model Context Protocol (MCP) Server Hub:
    Exposes standard MCP tool definitions and executes actions across SaaS backends.
    """
    
    def __init__(self):
        self.tools = {
            "crm_get_leads": self.crm_get_leads,
            "crm_get_lead_by_id": self.crm_get_lead_by_id,
            "crm_update_lead": self.crm_update_lead,
            "crm_create_deal": self.crm_create_deal,
            "billing_get_invoices": self.billing_get_invoices,
            "billing_charge_invoice": self.billing_charge_invoice,
            "billing_prepare_reminder": self.billing_prepare_reminder,
            "sheets_get_data": self.sheets_get_data,
            "sheets_append_row": self.sheets_append_row,
            "sheets_update_row": self.sheets_update_row,
            "sheets_delete_row": self.sheets_delete_row,
            "email_send_reminder": self.email_send_reminder,
        }

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "crm_get_leads",
                "description": "Fetch leads from CRM filtered by status or minimum lead score. "
                               "Returns {count, leads:[{id, name, email, score, status, ...}]}. "
                               "Reference a lead later via {{<this_step_id>.result.leads[0].id}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Optional status filter (e.g. QUALIFIED, PROPOSAL_SENT)"},
                        "min_score": {"type": "integer", "description": "Minimum lead score (0-100)"}
                    }
                }
            },
            {
                "name": "crm_update_lead",
                "description": "Update specific fields of a CRM lead (status, score, deal_value, notes). "
                               "Returns {success, lead_id, updated_lead:{...}, before:{...}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "The ID of the lead (e.g. LEAD-101)"},
                        "updates": {"type": "object", "description": "Dictionary of fields to update"}
                    },
                    "required": ["lead_id", "updates"]
                }
            },
            {
                "name": "crm_get_lead_by_id",
                "description": "Fetch a single CRM lead record by its exact lead ID. "
                               "Returns {found, lead:{id, name, email, score, status, ...}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "The ID of the lead (e.g. LEAD-104)"}
                    },
                    "required": ["lead_id"]
                }
            },
            {
                "name": "crm_create_deal",
                "description": "Create a new sales deal in the CRM for a qualified lead. "
                               "Returns {success, deal:{id, lead_id, title, amount, stage, ...}}. "
                               "Reference the created deal id via {{<this_step_id>.result.deal.id}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "Associated lead ID"},
                        "title": {"type": "string", "description": "Deal title"},
                        "amount": {"type": "number", "description": "Deal value in USD"},
                        "stage": {"type": "string", "description": "Pipeline stage (e.g. Contract Review)"}
                    },
                    "required": ["lead_id", "title"]
                }
            },
            {
                "name": "billing_get_invoices",
                "description": "Query billing portal invoices by payment status (OVERDUE, PAID, PENDING). "
                               "Returns {count, invoices:[{id, customer_email, amount_due, status, due_date, ...}]}. "
                               "Reference an invoice later via {{<this_step_id>.result.invoices[0].id}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Invoice status filter"}
                    }
                }
            },
            {
                "name": "billing_charge_invoice",
                "description": "Execute automatic payment charge against a customer invoice (CRITICAL RISK). "
                               "Returns {success, transaction:{txn_id, amount, status}, invoice:{id, status, ...}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Invoice ID to charge"},
                        "amount": {"type": "number", "description": "Amount to charge"}
                    },
                    "required": ["invoice_id"]
                }
            },
            {
                "name": "billing_prepare_reminder",
                "description": "Generate an overdue invoice reminder email payload without sending. "
                               "Returns {to_email, subject, body, invoice_details:{id, ...}}. "
                               "Reference the draft body via {{<this_step_id>.result.body}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Invoice ID"}
                    },
                    "required": ["invoice_id"]
                }
            },
            {
                "name": "sheets_get_data",
                "description": "Read rows from an executive spreadsheet or tracking log. "
                               "Returns {sheet, rows:[{Row, ...}]}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Name of the sheet tab"}
                    },
                    "required": ["sheet_name"]
                }
            },
            {
                "name": "sheets_append_row",
                "description": "Append a new row of operational data to a tracking sheet. "
                               "Returns {success, sheet_name, row_number, data}. "
                               "Reference the new row via {{<this_step_id>.result.row_number}}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Target sheet tab"},
                        "row_data": {"type": "object", "description": "Key-value row dictionary"}
                    },
                    "required": ["sheet_name", "row_data"]
                }
            },
            {
                "name": "sheets_update_row",
                "description": "Update existing rows in a sheet matching a filter key/value pair. "
                               "Returns {success, sheet_name, updated_count, rows:[{...}]}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Target sheet tab"},
                        "filter_key": {"type": "string", "description": "Column name to match (e.g. Account)"},
                        "filter_value": {"description": "Value to match in the filter column"},
                        "updates": {"type": "object", "description": "Key-value fields to overwrite"}
                    },
                    "required": ["sheet_name", "filter_key", "filter_value", "updates"]
                }
            },
            {
                "name": "sheets_delete_row",
                "description": "Delete a row from a sheet by row number (compensating/undo action).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Target sheet tab"},
                        "row_number": {"type": "integer", "description": "Row number to delete"}
                    },
                    "required": ["sheet_name", "row_number"]
                }
            },
            {
                "name": "email_send_reminder",
                "description": "Send an external email notification to a client (CRITICAL RISK). "
                               "Returns {dispatched, message_id, to, subject, status}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_email": {"type": "string", "description": "Recipient email"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body content"}
                    },
                    "required": ["to_email", "subject", "body"]
                }
            }
        ]

    # Tool Implementations
    def crm_get_leads(self, params: Dict[str, Any]) -> Dict[str, Any]:
        status = params.get("status")
        min_score = params.get("min_score")
        leads = mock_crm.get_leads(status=status, min_score=min_score)
        return {"count": len(leads), "leads": leads}

    def crm_get_lead_by_id(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lead_id = params.get("lead_id", "")
        lead = mock_crm.get_lead_by_id(lead_id)
        return {"found": lead is not None, "lead": lead}

    def crm_update_lead(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lead_id = params.get("lead_id")
        updates = params.get("updates", {})
        return mock_crm.update_lead(lead_id, updates)

    def crm_create_deal(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return mock_crm.create_deal(params)

    def billing_get_invoices(self, params: Dict[str, Any]) -> Dict[str, Any]:
        status = params.get("status")
        invoices = mock_billing.get_invoices(status=status)
        return {"count": len(invoices), "invoices": invoices}

    def billing_charge_invoice(self, params: Dict[str, Any]) -> Dict[str, Any]:
        invoice_id = params.get("invoice_id")
        return mock_billing.charge_invoice(invoice_id)

    def billing_prepare_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        invoice_id = params.get("invoice_id")
        return mock_billing.generate_reminder_payload(invoice_id)

    def sheets_get_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sheet_name = params.get("sheet_name", "Executive Ops Summary")
        return {"sheet": sheet_name, "rows": mock_sheets.get_sheet_data(sheet_name)}

    def sheets_append_row(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sheet_name = params.get("sheet_name", "Executive Ops Summary")
        row_data = params.get("row_data", {})
        return mock_sheets.append_row(sheet_name, row_data)

    def sheets_update_row(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sheet_name = params.get("sheet_name", "Executive Ops Summary")
        filter_key = params.get("filter_key", "Account")
        filter_val = params.get("filter_value", "")
        updates = params.get("updates", {})
        return mock_sheets.update_row(sheet_name, filter_key, filter_val, updates)

    def sheets_delete_row(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sheet_name = params.get("sheet_name", "Executive Ops Summary")
        row_number = int(params.get("row_number", -1))
        return mock_sheets.delete_row(sheet_name, row_number)

    def email_send_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Outbox dispatch simulation
        return {
            "dispatched": True,
            "timestamp": time.time(),
            "message_id": f"MSG-{int(time.time()*1000)}",
            "to": params.get("to_email"),
            "subject": params.get("subject"),
            "status": "SENT_VIA_MOCK_SMTP"
        }

    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self.tools:
            raise ValueError(f"MCP Tool '{tool_name}' not recognized.")
        return self.tools[tool_name](params)

mcp_hub = MCPToolHub()
