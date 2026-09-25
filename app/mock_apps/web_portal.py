def get_mock_portal_html(dom_version: str = "v1") -> str:
    """
    Returns an interactive mock web portal HTML.
    dom_version="v1": standard selectors (e.g. #submit-lead-btn)
    dom_version="v2": mutated selectors, changed class names, moved positions to trigger & verify self-healing!
    """
    btn_id = "submit-lead-btn" if dom_version == "v1" else "action-btn-alpha-99x"
    btn_class = "btn btn-primary" if dom_version == "v1" else "btn-styled-amber rounded-lg py-2"
    btn_text = "Submit Lead Sync" if dom_version == "v1" else "Confirm & Synchronize Record"
    
    extra_banner = ""
    if dom_version == "v2":
        extra_banner = """
        <div id="cookie-overlay-banner" style="background:#2d1b06; border:1px solid #d97706; padding:12px; margin-bottom:16px; border-radius:8px; color:#fde68a;">
            <strong>Notice:</strong> Layout shift simulated (DOM mutation active). Self-healing grounder should locate target by semantic text / AXTree.
            <button onclick="document.getElementById('cookie-overlay-banner').remove()" style="margin-left:12px; background:#d97706; color:#000; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">Dismiss Banner</button>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Enterprise Portal (DOM {dom_version})</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 24px;
            margin: 0;
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        h2 {{ color: #58a6ff; margin-top: 0; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
        }}
        th, td {{
            padding: 10px 12px;
            border: 1px solid #30363d;
            text-align: left;
        }}
        th {{ background: #21262d; color: #f0f6fc; }}
        input, select {{
            background: #0d1117;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 8px 12px;
            border-radius: 6px;
            width: 100%;
            box-sizing: border-box;
            margin-top: 6px;
            margin-bottom: 12px;
        }}
        button {{
            background: #238636;
            color: #ffffff;
            font-weight: 600;
            border: 1px solid rgba(240, 246, 252, 0.1);
            padding: 10px 18px;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button:hover {{ background: #2ea043; }}
        .badge-amber {{ background: #9e6a03; color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
        .badge-green {{ background: #238636; color: #fff; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
    </style>
</head>
<body>
    {extra_banner}
    <div class="card">
        <h2>Enterprise Operations Web Portal</h2>
        <p>Live target portal for autonomous agent interactions, web scraping, and form submission.</p>
        
        <form id="lead-intake-form" onsubmit="event.preventDefault(); document.getElementById('status-msg').innerText = 'Lead Submitted Successfully to Pipeline!';">
            <label for="company_name">Company Name</label>
            <input type="text" id="company_name" name="company_name" placeholder="e.g. Acme Corp" value="SolarGrid Systems">
            
            <label for="contact_email">Lead Contact Email</label>
            <input type="email" id="contact_email" name="contact_email" placeholder="email@domain.com" value="ops@solargrid.in">
            
            <label for="deal_tier">Deal Tier</label>
            <select id="deal_tier" name="deal_tier">
                <option value="Starter">Starter ($10k)</option>
                <option value="Enterprise" selected>Enterprise ($100k+)</option>
            </select>
            
            <button type="submit" id="{btn_id}" class="{btn_class}">{btn_text}</button>
        </form>
        <div id="status-msg" style="margin-top:14px; font-weight:bold; color:#3fb950;"></div>
    </div>

    <div class="card">
        <h3>Live Inventory & Portal Records</h3>
        <table id="portal-data-table">
            <thead>
                <tr>
                    <th>SKU ID</th>
                    <th>Product Title</th>
                    <th>Inventory Status</th>
                    <th>Price</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>SKU-8812</td>
                    <td>Industrial Optical Sensor Hub</td>
                    <td><span class="badge-green">In Stock</span></td>
                    <td>$1,450.00</td>
                </tr>
                <tr>
                    <td>SKU-8813</td>
                    <td>Edge Compute Node A100</td>
                    <td><span class="badge-amber">Low Stock (2 remaining)</span></td>
                    <td>$9,800.00</td>
                </tr>
            </tbody>
        </table>
    </div>
</body>
</html>
"""
