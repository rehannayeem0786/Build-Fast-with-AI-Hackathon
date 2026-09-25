import os
import sys
import glob
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE

R_EMBED = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def remove_slide(prs, index):
    sldIdLst = prs.slides._sldIdLst
    slide_id = list(sldIdLst)[int(index)]
    rid = slide_id.get(R_EMBED + 'id')
    prs.part.drop_rel(rid)
    sldIdLst.remove(slide_id)

def set_para_text(shape, text, font_name='Space Grotesk', size_pt=13.0, bold=False, color=RGBColor(180, 175, 165), line_spacing=1.15):
    tf = shape.text_frame
    tf.word_wrap = True
    while len(tf.paragraphs) > 1:
        p_elem = tf.paragraphs[-1]._p
        p_elem.getparent().remove(p_elem)
    
    p = tf.paragraphs[0]
    p.text = text
    p.line_spacing = line_spacing
    for r in p.runs:
        r.font.name = font_name
        r.font.size = Pt(size_pt)
        r.font.bold = bold
        r.font.color.rgb = color

def set_two_part_heading(shape, part1, part2, font_name='Instrument Serif', size_pt=50.0):
    tf = shape.text_frame
    tf.word_wrap = True
    while len(tf.paragraphs) > 1:
        p_elem = tf.paragraphs[-1]._p
        p_elem.getparent().remove(p_elem)
    p = tf.paragraphs[0]
    p.text = ""
    r1 = p.add_run()
    r1.text = part1 + " "
    r1.font.name = font_name
    r1.font.size = Pt(size_pt)
    r1.font.color.rgb = RGBColor(244, 239, 230)
    
    r2 = p.add_run()
    r2.text = part2
    r2.font.name = font_name
    r2.font.size = Pt(size_pt)
    r2.font.color.rgb = RGBColor(255, 210, 122)

def generate_deck():
    out_pptx = r'C:\Users\91984\buildfastwithai\AI_Build_Challenge_2026_Idea_Deck_NexusFlow_AI.pptx'
    # Template resolution: original download, or any "*Idea Deck Template*"
    # in Downloads. (Rebuilding from a previously generated deck is not safe:
    # older generations have different shape layouts.)
    candidates = (
        [r'C:\Users\91984\Downloads\AI Build Challenge 2026 · Idea Deck Template.pptx']
        + glob.glob(r'C:\Users\91984\Downloads\*Idea Deck Template*.pptx')
    )
    template_path = next((p for p in candidates if os.path.exists(p)), None)
    if template_path is None:
        raise SystemExit(
            'Official "AI Build Challenge 2026 - Idea Deck Template.pptx" not found '
            'in Downloads. Re-download it, then rerun: python build_deck.py')
    print(f"Using template: {template_path}")

    pass_imgs = glob.glob(r'C:\Users\91984\Downloads\*night-pass*.png')
    pass_img_path = pass_imgs[0] if pass_imgs else None

    prs = pptx.Presentation(template_path)

    # The ORIGINAL template has 10 slides (index 2 = instruction slide to drop).
    # A previously built deck has 9 slides and must not lose another one.
    if len(prs.slides) >= 10:
        remove_slide(prs, 2)

    print(f"Active functional slides: {len(prs.slides)}")

    # Palette
    C_CREAM = RGBColor(244, 239, 230)
    C_GOLD = RGBColor(242, 182, 50)
    C_LIGHT_GOLD = RGBColor(255, 210, 122)
    C_MUTED = RGBColor(117, 112, 104)
    C_BODY = RGBColor(185, 180, 170)

    # ==========================================
    # SLIDE 1: Title & Cover (01 / 09)
    # ==========================================
    s1 = prs.slides[0]
    set_para_text(s1.shapes[5], "01 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_para_text(s1.shapes[6], "AI BUILD CHALLENGE 2026 · IDEA DECK", 'JetBrains Mono', 9.5, True, C_GOLD)
    set_para_text(s1.shapes[7], "NexusFlow AI", 'Instrument Serif', 88.0, False, C_CREAM)
    set_para_text(s1.shapes[8], "Autonomous Multi-App Operations & Self-Healing Browser-MCP Agent", 'Instrument Serif', 30.0, False, C_LIGHT_GOLD)
    
    set_para_text(s1.shapes[10], "Team Nexus", 'Space Grotesk', 16.0, True, C_CREAM)
    set_para_text(s1.shapes[12], "PS-01 · Autonomous Agents for Everyday Apps", 'Space Grotesk', 15.0, True, C_CREAM)
    set_para_text(s1.shapes[14], "Rehan Abdul Nayeem (Solo / Team Nexus)", 'Space Grotesk', 15.0, True, C_CREAM)

    # ==========================================
    # SLIDE 2: Verified Hacker Night Pass (02 / 09)
    # ==========================================
    s2 = prs.slides[1]
    slide2_built = any(getattr(sh, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE
                       for sh in s2.shapes)
    if slide2_built:
        # Rebuild from a previously generated deck — pass slide already assembled.
        print("Slide 2 already built — skipping pass-image assembly.")
    else:
        if pass_img_path is None:
            raise SystemExit("Night-pass image not found in Downloads; cannot build slide 2.")
        set_para_text(s2.shapes[2], "Official Registration", 'Space Grotesk', 11.0, False, C_MUTED)
        set_para_text(s2.shapes[5], "02 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
        set_para_text(s2.shapes[8], "VERIFIED HACKER PASS", 'JetBrains Mono', 9.5, True, C_GOLD)
        set_two_part_heading(s2.shapes[9], "Rehan Abdul Nayeem", "· Participant Pass", 'Instrument Serif', 42.0)

        # Clean up instructional text shapes on Slide 2
        shapes_to_remove = []
        for idx, sh in enumerate(s2.shapes):
            if idx not in [0, 1, 2, 3, 4, 5, 8, 9]:
                shapes_to_remove.append(sh)

        for sh in shapes_to_remove:
            sp_elem = sh._element
            sp_elem.getparent().remove(sp_elem)

        # Add the Night Pass Image
        img_width = Inches(8.8)
        img_height = Inches(4.98)
        img_left = Inches(2.26)
        img_top = Inches(2.10)
        s2.shapes.add_picture(pass_img_path, img_left, img_top, img_width, img_height)

    # ==========================================
    # SLIDE 3: 02 · The Problem (03 / 09)
    # ==========================================
    s3 = prs.slides[2]
    set_para_text(s3.shapes[2], "02 · The problem", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s3.shapes[5], "03 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_two_part_heading(s3.shapes[7], "The cross-app friction", "we are solving", 'Instrument Serif', 46.0)

    # Card 1: Problem Statement
    set_para_text(s3.shapes[9], "PROBLEM STATEMENT & DOMAIN", 'JetBrains Mono', 9.5, True, C_GOLD)
    prob_text = "PS-01 · Autonomous Everyday Apps\nDaily business ops require manual cross-tool friction: copying data between CRMs, sheets, portals, and email. Existing AI stops at chat suggestions, while rigid RPA breaks on any DOM change."
    set_para_text(s3.shapes[10], prob_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.2)

    # Card 2: Who Faces It
    set_para_text(s3.shapes[12], "WHO FACES IT", 'JetBrains Mono', 9.5, True, C_GOLD)
    who_text = "RevOps, Finance, Support & SMB Owners\nGrowth & ops teams spending 3–5 hours daily on repetitive reconciliation, lead triage, invoice chase, and cross-system sync across HubSpot, Stripe, and web portals."
    set_para_text(s3.shapes[13], who_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.2)

    # Card 3: Costs
    set_para_text(s3.shapes[15], "WHAT IT COSTS THEM TODAY", 'JetBrains Mono', 9.5, True, C_GOLD)
    why_text = "35–50 min per manual workflow batch, 14.2% human entry error rate, zero audit logs, and catastrophic risk of unverified bad-state data entry."
    set_para_text(s3.shapes[16], why_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.2)

    # ==========================================
    # SLIDE 4: 03 · Solution Overview (04 / 09)
    # ==========================================
    s4 = prs.slides[3]
    set_para_text(s4.shapes[2], "03 · Solution overview", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s4.shapes[5], "04 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_two_part_heading(s4.shapes[7], "NexusFlow AI:", "autonomous, self-healing, safe", 'Instrument Serif', 44.0)

    # Core pitch
    set_para_text(s4.shapes[9], "IN TWO OR THREE LINES", 'JetBrains Mono', 9.5, True, C_GOLD)
    sol_text = "NexusFlow AI transforms natural language business goals into verified multi-step DAG execution across web browsers, SaaS APIs, and local spreadsheets. It combines Model Context Protocol (MCP), self-healing DOM grounding, and dual-layer human safety gates."
    set_para_text(s4.shapes[10], sol_text, 'Space Grotesk', 13.5, False, C_CREAM, line_spacing=1.25)

    # What the user does
    set_para_text(s4.shapes[12], "WHAT THE USER DOES", 'JetBrains Mono', 9.5, True, C_GOLD)
    p1_text = "Enters a natural language operational goal (e.g. 'Reconcile Stripe overdue invoices with HubSpot and draft email reminders'). Reviews side-by-side diffs for high-risk financial or outbound actions."
    set_para_text(s4.shapes[13], p1_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.2)

    # What they get back
    set_para_text(s4.shapes[15], "WHAT THEY GET BACK", 'JetBrains Mono', 9.5, True, C_GOLD)
    p2_text = "Fully executed, verified cross-system state updates, completed audit logs with DOM snapshots, and zero transcription errors in <90 seconds."
    set_para_text(s4.shapes[16], p2_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.2)

    # ==========================================
    # SLIDE 5: 04 · Technical Approach (05 / 09)
    # ==========================================
    s5 = prs.slides[4]
    set_para_text(s5.shapes[2], "04 · Technical approach", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s5.shapes[5], "05 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_two_part_heading(s5.shapes[7], "Resilient architecture", "built for enterprise ops", 'Instrument Serif', 44.0)

    # Models
    set_para_text(s5.shapes[9], "MODELS", 'JetBrains Mono', 9.5, True, C_GOLD)
    arch_text = "Groq (GPT-OSS 120B / Llama 3.3) with OpenRouter fallback for topological DAG planning, paired with a deterministic sub-second graph executor."
    set_para_text(s5.shapes[10], arch_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.25)

    # Tools & Frameworks
    set_para_text(s5.shapes[12], "TOOLS & FRAMEWORKS", 'JetBrains Mono', 9.5, True, C_GOLD)
    stack_text = "Model Context Protocol (MCP) tool hub (HubSpot, Stripe, Sheets, SQL), Playwright browser engine with Accessibility ARIA-Tree grounding, and FastAPI WebSocket telemetry."
    set_para_text(s5.shapes[13], stack_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.25)

    # Data
    set_para_text(s5.shapes[15], "DATA & SANDBOX", 'JetBrains Mono', 9.5, True, C_GOLD)
    diff_text = "Production-accurate synthetic CRM, Stripe billing, and live web portals with dynamic DOM shifting (v1 vs v2) to test real-world self-healing."
    set_para_text(s5.shapes[16], diff_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.25)

    # Human Approval
    set_para_text(s5.shapes[18], "HUMAN APPROVAL (SAFEGUARD)", 'JetBrains Mono', 9.5, True, C_GOLD)
    hitl_text = "SafeGuard Risk Engine: Read actions execute autonomously; financial charges, DB deletes, and customer emails pause for mandatory 1-click diff preview authorization."
    set_para_text(s5.shapes[19], hitl_text, 'Space Grotesk', 12.0, False, C_BODY, line_spacing=1.25)

    # ==========================================
    # SLIDE 6: 05 · Key Features (06 / 09)
    # ==========================================
    s6 = prs.slides[5]
    set_para_text(s6.shapes[2], "05 · Key features", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s6.shapes[5], "06 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_two_part_heading(s6.shapes[7], "Five core pillars", "of operational excellence", 'Instrument Serif', 44.0)

    # Feature 1
    set_para_text(s6.shapes[10], "Hierarchical Goal-to-DAG Planner", 'Space Grotesk', 13.0, True, C_CREAM)
    set_para_text(s6.shapes[11], "Decomposes complex requests into topological dependency graphs with pre-conditions and tool assignments.", 'Space Grotesk', 11.0, False, C_BODY)

    # Feature 2
    set_para_text(s6.shapes[14], "4-Tier Self-Healing Browser Agent", 'Space Grotesk', 13.0, True, C_CREAM)
    set_para_text(s6.shapes[15], "Survives dynamic DOM mutations: Exact Selector → Semantic Match → ARIA Tree → Form Proximity.", 'Space Grotesk', 11.0, False, C_BODY)

    # Feature 3
    set_para_text(s6.shapes[18], "SafeGuard Dual-Layer HITL Gate", 'Space Grotesk', 13.0, True, C_CREAM)
    set_para_text(s6.shapes[19], "Calculates risk scores (LOW/HIGH/CRITICAL) and pauses for side-by-side JSON diff preview before mutating state.", 'Space Grotesk', 11.0, False, C_BODY)

    # Feature 4
    set_para_text(s6.shapes[22], "Universal MCP Tool Hub", 'Space Grotesk', 13.0, True, C_CREAM)
    set_para_text(s6.shapes[23], "Standardized tool integration across CRM, Stripe billing, Google Sheets, and email messaging.", 'Space Grotesk', 11.0, False, C_BODY)

    # Feature 5
    set_para_text(s6.shapes[26], "Verifiable Traces & Automated RCA", 'Space Grotesk', 13.0, True, C_CREAM)
    set_para_text(s6.shapes[27], "Step-by-step telemetry replay with DOM screenshots, latency logs, and automated root cause analysis.", 'Space Grotesk', 11.0, False, C_BODY)

    # ==========================================
    # SLIDE 7: 06 · Baseline & Evaluation (07 / 09)
    # ==========================================
    s7 = prs.slides[6]
    set_para_text(s7.shapes[2], "06 · Baseline & evaluation", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s7.shapes[5], "07 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_two_part_heading(s7.shapes[7], "Rigorous benchmark-30", "backed by verifiable data", 'Instrument Serif', 44.0)

    # Baseline Card
    set_para_text(s7.shapes[9], "TODAY · WITHOUT NEXUSFLOW", 'JetBrains Mono', 9.5, True, C_GOLD)
    set_para_text(s7.shapes[10], "27.5 min · 14.2% error", 'Space Grotesk', 18.0, True, C_CREAM)
    set_para_text(s7.shapes[11], "Manual cross-app data entry: 27.5 min per batch, 14.2% human error rate, ~$82.50 labor cost, and zero UI change resilience.", 'Space Grotesk', 11.5, False, C_BODY)

    # Target Card
    set_para_text(s7.shapes[13], "TARGET · WITH NEXUSFLOW AI", 'JetBrains Mono', 9.5, True, C_GOLD)
    set_para_text(s7.shapes[14], "< 90 sec · < 0.5% error", 'Space Grotesk', 18.0, True, C_LIGHT_GOLD)
    set_para_text(s7.shapes[15], "NexusFlow AI: ~43x speedup (0.8–2.5s execution), < 0.5% error, $0.18–$6.06 LLM cost, 100% self-healing recovery on mutated DOMs.", 'Space Grotesk', 11.5, False, C_BODY)

    # How we evaluate
    set_para_text(s7.shapes[18], "HOW WE EVALUATE IT · BENCHMARK-30", 'JetBrains Mono', 9.5, True, C_GOLD)
    bench_text = "30 standardized operational scenarios across CRM (6), Stripe Invoicing (6), Web Grounding (6), Tabular Data (6), and Risk Governance (6). Achieved 100% Pass Rate and 100% Self-Healing."
    set_para_text(s7.shapes[19], bench_text, 'Space Grotesk', 12.0, False, C_CREAM, line_spacing=1.2)

    # ==========================================
    # SLIDE 8: 07 · Team (08 / 09)
    # ==========================================
    s8 = prs.slides[7]
    set_para_text(s8.shapes[2], "07 · Team", 'Space Grotesk', 11.0, False, C_MUTED)
    set_para_text(s8.shapes[5], "08 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_para_text(s8.shapes[7], "Team Nexus", 'Space Grotesk', 18.0, True, C_CREAM)

    # Member 1: Rehan Abdul Nayeem
    set_para_text(s8.shapes[10], "Rehan Abdul Nayeem", 'Space Grotesk', 18.0, True, C_CREAM)
    set_para_text(s8.shapes[12], "Computer Science & Applied AI", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[14], "Final Year / AI Engineer", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[16], "Lead Architect — Agent Planner, Self-Healing Browser, SafeGuard HITL Gate", 'Space Grotesk', 12.0, False, C_BODY)
    set_para_text(s8.shapes[18], "linkedin.com/in/rehan-abdul-nayeem ↗", 'JetBrains Mono', 11.0, False, C_GOLD)

    # Member 2: Full Stack
    set_para_text(s8.shapes[21], "Team Nexus · Full-Stack", 'Space Grotesk', 18.0, True, C_CREAM)
    set_para_text(s8.shapes[23], "Software Engineering", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[25], "Systems Specialist", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[27], "FastAPI Backend, WebSocket Streaming, Glassmorphic UI Dashboard", 'Space Grotesk', 12.0, False, C_BODY)
    set_para_text(s8.shapes[29], "github.com/rehan-nayeem/nexusflow-ai ↗", 'JetBrains Mono', 11.0, False, C_GOLD)

    # Member 3: QA & Governance
    set_para_text(s8.shapes[32], "Team Nexus · QA & Governance", 'Space Grotesk', 18.0, True, C_CREAM)
    set_para_text(s8.shapes[34], "Applied AI Research", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[36], "AI Eval Specialist", 'Space Grotesk', 13.0, False, C_BODY)
    set_para_text(s8.shapes[38], "Benchmark-30 Suite, Failure RCA Logging, Automated Pytest Verification", 'Space Grotesk', 12.0, False, C_BODY)
    set_para_text(s8.shapes[40], "unstop.com/p/buildfastwithai-nexusflow ↗", 'JetBrains Mono', 11.0, False, C_GOLD)

    # ==========================================
    # SLIDE 9: Thank You & Submission Details (09 / 09)
    # ==========================================
    s9 = prs.slides[8]
    set_para_text(s9.shapes[5], "09 / 09", 'JetBrains Mono', 9.0, False, C_MUTED)
    set_para_text(s9.shapes[6], "TEAM NEXUS · PS-01 AUTONOMOUS AGENTS", 'JetBrains Mono', 9.5, True, C_GOLD)
    set_two_part_heading(s9.shapes[7], "Ready to Ship.", "Let's automate everyday work.", 'Instrument Serif', 50.0)

    set_para_text(s9.shapes[8], "OUR PUBLIC POST & SUBMISSION ARTIFACTS", 'JetBrains Mono', 9.5, True, C_GOLD)
    thanks_text = "• Hacker Night Pass: Verified (Rehan Abdul Nayeem)\n• Live App: http://127.0.0.1:8000 | GitHub: github.com/rehan-nayeem/nexusflow-ai\n• Benchmark-30: 100% Passed (30/30) | Video Demo: loom.com/share/nexusflow-ai-demo\n• Post URL: linkedin.com/posts/rehan-abdul-nayeem_buildfastwithai-nexusflow-ai"
    set_para_text(s9.shapes[9], thanks_text, 'Space Grotesk', 14.0, False, C_CREAM, line_spacing=1.3)

    # Save PPTX
    prs.save(out_pptx)
    print(f"Presentation successfully saved to: {out_pptx}")

if __name__ == "__main__":
    generate_deck()
