import time
from typing import Dict, List, Any, Optional

class MockCRMDatabase:
    def __init__(self):
        self.leads = [
            {"id": "LEAD-101", "name": "Sarah Chen", "email": "sarah.c@techcorp.io", "company": "TechCorp", "score": 88, "status": "QUALIFIED", "deal_value": 45000, "assigned_rep": "Alex Rivera", "last_contact": "2026-09-20"},
            {"id": "LEAD-102", "name": "Marcus Vance", "email": "mvance@apexscale.com", "company": "ApexScale", "score": 94, "status": "PROPOSAL_SENT", "deal_value": 78000, "assigned_rep": "Elena Rostova", "last_contact": "2026-09-22"},
            {"id": "LEAD-103", "name": "David Kim", "email": "dkim@quantumops.ai", "company": "QuantumOps", "score": 72, "status": "CONTACTED", "deal_value": 30000, "assigned_rep": "Alex Rivera", "last_contact": "2026-09-18"},
            {"id": "LEAD-104", "name": "Priya Sharma", "email": "psharma@solargrid.in", "company": "SolarGrid India", "score": 96, "status": "QUALIFIED", "deal_value": 110000, "assigned_rep": "Elena Rostova", "last_contact": "2026-09-24"},
            {"id": "LEAD-105", "name": "Jason Bourne", "email": "jbourne@treadstone.org", "company": "Treadstone Media", "score": 45, "status": "COLD", "deal_value": 15000, "assigned_rep": "Unassigned", "last_contact": "2026-08-10"},
            {"id": "LEAD-106", "name": "Chloe Bennett", "email": "cbennett@cloudshield.net", "company": "CloudShield", "score": 91, "status": "NEGOTIATION", "deal_value": 62000, "assigned_rep": "Alex Rivera", "last_contact": "2026-09-23"},
        ]
        self.deals = [
            {"id": "DEAL-501", "lead_id": "LEAD-102", "title": "ApexScale Enterprise Migration", "amount": 78000, "stage": "Proposal Sent", "probability": 0.75, "close_date": "2026-10-15"},
            {"id": "DEAL-502", "lead_id": "LEAD-104", "title": "SolarGrid Pan-India Rollout", "amount": 110000, "stage": "Contract Review", "probability": 0.90, "close_date": "2026-10-05"},
            {"id": "DEAL-503", "lead_id": "LEAD-106", "title": "CloudShield Security Suite", "amount": 62000, "stage": "Discovery Call", "probability": 0.40, "close_date": "2026-11-01"},
        ]
        self.activity_log: List[Dict[str, Any]] = []

    def get_leads(self, status: Optional[str] = None, min_score: Optional[int] = None) -> List[Dict[str, Any]]:
        results = self.leads
        if status:
            results = [l for l in results if l["status"].upper() == status.upper()]
        if min_score is not None:
            results = [l for l in results if l["score"] >= min_score]
        return results

    def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        for l in self.leads:
            if l["id"] == lead_id:
                return l
        return None

    def update_lead(self, lead_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        lead = self.get_lead_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found in CRM.")
        
        before_state = dict(lead)
        lead.update(updates)
        self.activity_log.append({
            "timestamp": time.time(),
            "action": "UPDATE_LEAD",
            "lead_id": lead_id,
            "before": before_state,
            "after": dict(lead)
        })
        return {"success": True, "lead_id": lead_id, "updated_lead": lead, "before": before_state}

    def create_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        deal_id = f"DEAL-{len(self.deals) + 501}"
        new_deal = {
            "id": deal_id,
            "lead_id": deal_data.get("lead_id", ""),
            "title": deal_data.get("title", "Untitled Deal"),
            "amount": deal_data.get("amount", 0),
            "stage": deal_data.get("stage", "Draft"),
            "probability": deal_data.get("probability", 0.5),
            "close_date": deal_data.get("close_date", "2026-10-30")
        }
        self.deals.append(new_deal)
        self.activity_log.append({
            "timestamp": time.time(),
            "action": "CREATE_DEAL",
            "deal_id": deal_id,
            "deal_data": new_deal
        })
        return {"success": True, "deal": new_deal}

mock_crm = MockCRMDatabase()
