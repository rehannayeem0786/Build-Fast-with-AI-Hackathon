import time
from typing import Dict, List, Any, Optional

class MockSheetsDatabase:
    def __init__(self):
        self.sheets: Dict[str, List[Dict[str, Any]]] = {
            "Executive Ops Summary": [
                {"Row": 1, "Account": "TechCorp", "Region": "NA", "ARR": 45000, "Health": "Amber", "Action Required": "Invoice Overdue"},
                {"Row": 2, "Account": "ApexScale", "Region": "EMEA", "ARR": 78000, "Health": "Green", "Action Required": "None"},
                {"Row": 3, "Account": "SolarGrid India", "Region": "APAC", "ARR": 110000, "Health": "Amber", "Action Required": "Payment Followup"},
            ],
            "Audit Trail Log": []
        }

    def list_sheets(self) -> List[str]:
        return list(self.sheets.keys())

    def get_sheet_data(self, sheet_name: str) -> List[Dict[str, Any]]:
        if sheet_name not in self.sheets:
            self.sheets[sheet_name] = []
        return self.sheets[sheet_name]

    def append_row(self, sheet_name: str, row_data: Dict[str, Any]) -> Dict[str, Any]:
        if sheet_name not in self.sheets:
            self.sheets[sheet_name] = []
        
        row_number = len(self.sheets[sheet_name]) + 1
        row_entry = {"Row": row_number, **row_data}
        self.sheets[sheet_name].append(row_entry)
        return {"success": True, "sheet_name": sheet_name, "row_number": row_number, "data": row_entry}

    def update_row(self, sheet_name: str, filter_key: str, filter_value: Any, updates: Dict[str, Any]) -> Dict[str, Any]:
        if sheet_name not in self.sheets:
            raise ValueError(f"Sheet {sheet_name} does not exist.")
        
        updated_rows = []
        for row in self.sheets[sheet_name]:
            if str(row.get(filter_key, "")) == str(filter_value):
                row.update(updates)
                updated_rows.append(row)
        
        return {"success": True, "sheet_name": sheet_name, "updated_count": len(updated_rows), "rows": updated_rows}

    def delete_row(self, sheet_name: str, row_number: int) -> Dict[str, Any]:
        """Compensating action used by workflow undo/rollback."""
        if sheet_name not in self.sheets:
            raise ValueError(f"Sheet {sheet_name} does not exist.")

        rows = self.sheets[sheet_name]
        for i, row in enumerate(rows):
            if str(row.get("Row")) == str(row_number):
                removed = rows.pop(i)
                # Keep Row numbers contiguous after removal
                for j in range(i, len(rows)):
                    rows[j]["Row"] = j + 1
                return {"success": True, "sheet_name": sheet_name, "removed": removed}

        return {"success": False, "error": f"Row {row_number} not found in '{sheet_name}'."}

mock_sheets = MockSheetsDatabase()
