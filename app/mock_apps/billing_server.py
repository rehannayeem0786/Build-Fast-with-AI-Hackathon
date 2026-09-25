import time
from typing import Dict, List, Any, Optional

class MockBillingDatabase:
    def __init__(self):
        self.invoices = [
            {"id": "INV-2026-001", "customer_email": "sarah.c@techcorp.io", "amount_due": 4500.00, "status": "OVERDUE", "due_date": "2026-09-15", "currency": "USD", "items": ["Enterprise Tier Monthly", "Addon Seats x 10"]},
            {"id": "INV-2026-002", "customer_email": "mvance@apexscale.com", "amount_due": 12500.00, "status": "PAID", "due_date": "2026-09-20", "currency": "USD", "items": ["Annual Platform License"]},
            {"id": "INV-2026-003", "customer_email": "psharma@solargrid.in", "amount_due": 8900.00, "status": "OVERDUE", "due_date": "2026-09-10", "currency": "USD", "items": ["IoT Gateway Connector Support"]},
            {"id": "INV-2026-004", "customer_email": "cbennett@cloudshield.net", "amount_due": 3400.00, "status": "OVERDUE", "due_date": "2026-09-18", "currency": "USD", "items": ["Cloud SOC Monitoring"]},
            {"id": "INV-2026-005", "customer_email": "dkim@quantumops.ai", "amount_due": 1500.00, "status": "PENDING", "due_date": "2026-09-30", "currency": "USD", "items": ["Starter License Pack"]},
        ]
        self.transactions: List[Dict[str, Any]] = []

    def get_invoices(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return [inv for inv in self.invoices if inv["status"].upper() == status.upper()]
        return self.invoices

    def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        for inv in self.invoices:
            if inv["id"] == invoice_id:
                return inv
        return None

    def charge_invoice(self, invoice_id: str, payment_method: str = "card_auto") -> Dict[str, Any]:
        inv = self.get_invoice_by_id(invoice_id)
        if not inv:
            raise ValueError(f"Invoice {invoice_id} not found.")
        
        before_state = dict(inv)
        inv["status"] = "PAID"
        inv["paid_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        txn = {
            "txn_id": f"TXN-{int(time.time()*1000)}",
            "invoice_id": invoice_id,
            "amount": inv["amount_due"],
            "currency": inv["currency"],
            "status": "SUCCESS",
            "payment_method": payment_method
        }
        self.transactions.append(txn)
        return {"success": True, "transaction": txn, "invoice": inv, "before": before_state}

    def generate_reminder_payload(self, invoice_id: str) -> Dict[str, Any]:
        inv = self.get_invoice_by_id(invoice_id)
        if not inv:
            raise ValueError(f"Invoice {invoice_id} not found.")
        
        return {
            "to_email": inv["customer_email"],
            "subject": f"Notice: Overdue Invoice {inv['id']} for {inv['currency']} {inv['amount_due']}",
            "body": f"Dear Customer,\n\nThis is a notification that invoice {inv['id']} of amount {inv['currency']} {inv['amount_due']} was due on {inv['due_date']}.\n\nPlease remit payment at your earliest convenience.\n\nBest regards,\nFinance & Operations",
            "invoice_details": inv
        }

mock_billing = MockBillingDatabase()
