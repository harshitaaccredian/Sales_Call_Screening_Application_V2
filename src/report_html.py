"""Generate a self-contained HTML report from a call-quality report JSON file.

Usage:
    python src/report_html.py output/0.report.json
    # writes output/0.report.html
"""

import json
import os
import sys
from html import escape as html_escape
from src.report_methodology import methodology_css, render_methodology_section
from src.report_tabs import tabs_css, render_tabs

CHAPTERS = {
    "customer_profiling": "Ch 5", "need_identification": "Ch 6",
    "vision_setting": "Ch 7",     "program_mapping": "Ch 8",
    "fee_and_urgency": "Ch 9",    "objection_handling": "Ch 10",
    "trust_journey": "Framework 4",
}

def escape(s):
    if s is None:
        return ""
    return html_escape(str(s))


SEV_LABELS = {"L1": "Minor", "L2": "Major", "L3": "Critical", "None": "Clean"}
SEV_BADGE_CLASS = {"L1": "sev-L1", "L2": "sev-L2", "L3": "sev-L3", "None": "sev-None"}
PRIORITY_CLASS = {"Immediate": "immediate", "Short-term": "short-term", "Follow-up": "follow-up"}

CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #334155;
      background: #f8fafc;
      -webkit-font-smoothing: antialiased;
    }

    .page { max-width: 1200px; margin: 0 auto; padding: 40px 24px 80px; }

    .header {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #fff;
      border-radius: 16px;
      padding: 36px 40px;
      margin-bottom: 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .header-left h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; letter-spacing: -0.5px; color: #f8fafc; }
    .header-left .subtitle { font-size: 14px; color: #94a3b8; font-weight: 500; }
    .header-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
    
    .flag-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: 700;
      letter-spacing: 0.5px; text-transform: uppercase;
    }
    .flag-badge.flagged { background: #ef4444; color: #fff; }
    .flag-badge.clean   { background: #10b981; color: #fff; }
    
    .severity-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 700;
    }
    .sev-L1   { background: #fef3c7; color: #d97706; }
    .sev-L2   { background: #ffedd5; color: #ea580c; }
    .sev-L3   { background: #fee2e2; color: #dc2626; }
    .sev-None { background: #ecfdf5; color: #059669; }

    .section { margin-bottom: 36px; }
    .section-title {
      font-size: 14px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 1px; color: #1e3a8a;
      margin-bottom: 16px; padding-bottom: 8px;
      border-bottom: 2px solid #e2e8f0;
    }

    .card {
      background: #fff;
      border-radius: 12px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
      padding: 28px 32px;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 20px;
    }
    .meta-item { display: flex; flex-direction: column; gap: 4px; }
    .meta-label { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
    .meta-value { font-size: 14px; font-weight: 600; color: #1e293b; }
    .meta-value.null-val { color: #cbd5e1; font-style: italic; font-weight: 400; }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 16px;
    }
    .stat-card {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 18px 20px;
      display: flex; flex-direction: column; gap: 6px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    .stat-label { font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-value { font-size: 22px; font-weight: 800; color: #0f172a; line-height: 1.2; }
    .stat-sub   { font-size: 12px; color: #64748b; font-weight: 500; }

    .ratio-bar-wrap { margin-top: 8px; }
    .ratio-bar {
      height: 8px; border-radius: 4px;
      background: #e2e8f0; overflow: hidden;
      display: flex;
    }
    .ratio-rep  { background: #1e3a8a; height: 100%; }
    .ratio-cust { background: #38bdf8; height: 100%; }
    .ratio-legend { display: flex; gap: 14px; margin-top: 8px; font-size: 12px; color: #475569; font-weight: 600; }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }

    .summary-pills { display: flex; gap: 16px; flex-wrap: wrap; }
    .pill {
      display: flex; align-items: center; gap: 14px;
      padding: 12px 24px; border-radius: 10px; font-weight: 700; min-width: 140px;
    }
    .pill-count { font-size: 28px; font-weight: 800; }
    .pill-label { font-size: 12px; line-height: 1.4; font-weight: 600; }
    .pill.l1    { background: #fffbeb; color: #d97706; border: 1px solid #fef3c7; }
    .pill.l2    { background: #fff7ed; color: #ea580c; border: 1px solid #ffedd5; }
    .pill.l3    { background: #fef2f2; color: #dc2626; border: 1px solid #fee2e2; }
    .pill.total { background: #f0fdfa; color: #0f766e; border: 1px solid #ccfbf1; }

    .incident-card {
      border-radius: 12px;
      border-left: 6px solid;
      background: #fff;
      box-shadow: 0 2px 4px rgba(0,0,0,0.04);
      border: 1px solid #e2e8f0;
      border-left-width: 6px;
      padding: 24px;
      margin-bottom: 18px;
    }
    .incident-card.sev-L1 { border-left-color: #f59e0b; }
    .incident-card.sev-L2 { border-left-color: #ea580c; }
    .incident-card.sev-L3 { border-left-color: #dc2626; }

    .incident-header {
      display: flex; align-items: center; gap: 14px;
      margin-bottom: 16px; flex-wrap: wrap;
    }
    .incident-id { font-size: 12px; font-weight: 800; color: #94a3b8; text-transform: uppercase; }
    .incident-category { font-size: 15px; font-weight: 700; color: #0f172a; }
    .incident-ts {
      margin-left: auto; font-size: 11px; font-weight: 700;
      background: #f1f5f9; color: #475569;
      padding: 3px 10px; border-radius: 6px; text-transform: uppercase;
    }

    .incident-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 14px;
    }
    @media (max-width: 768px) { .incident-grid { grid-template-columns: 1fr; } }

    .incident-field { display: flex; flex-direction: column; gap: 4px; }
    .field-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; }
    .field-value { font-size: 14px; color: #334155; font-weight: 500; }
    .field-value.correct { color: #16a34a; font-weight: 600; }

    .transcript-quote {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px 18px;
      font-size: 13px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      color: #475569;
      margin-top: 10px;
      word-break: break-word;
    }

    .violation-basis {
      background: #fffbeb;
      border: 1px solid #fef3c7;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      color: #b45309;
      margin-top: 10px;
      font-weight: 500;
    }

    .checklist-table { width: 100%; border-collapse: collapse; }
    .checklist-table th {
      text-align: left; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: #64748b; padding: 12px 16px;
      background: #f8fafc; border-bottom: 2px solid #e2e8f0;
    }
    .checklist-table td { padding: 14px 16px; border-bottom: 1px solid #f1f5f9; font-size: 13px; color: #334155; }
    .checklist-table tr:last-child td { border-bottom: none; }
    .checklist-table tr.cat-header td {
      font-weight: 700; font-size: 13px; color: #1e3a8a;
      background: #f1f5f9; padding: 10px 16px;
    }
    .status-pass { color: #16a34a; font-weight: 700; }
    .status-fail { color: #dc2626; font-weight: 700; }
    .status-nd   { color: #94a3b8; font-weight: 500; }
    .inc-ref-link {
      display: inline-block;
      font-size: 11px; font-weight: 700;
      background: #ffedd5; color: #ea580c;
      padding: 2px 8px; border-radius: 12px;
    }

    .assessment-text { font-size: 14px; line-height: 1.8; color: #334155; font-weight: 500; }

    .rule-box {
      background: #fef2f2;
      border: 1px solid #fee2e2;
      border-radius: 8px;
      padding: 14px 18px;
      font-weight: 700; font-size: 14px; color: #991b1b;
      margin-bottom: 20px;
    }
    .action-list { display: flex; flex-direction: column; gap: 10px; }
    .action-item {
      display: flex; align-items: center; gap: 14px;
      padding: 12px 18px; border-radius: 8px;
    }
    .action-item.immediate  { background: #fff1f2; border: 1px solid #fecdd3; }
    .action-item.short-term { background: #fffbeb; border: 1px solid #fef3c7; }
    .action-item.follow-up  { background: #f0f9ff; border: 1px solid #bae6fd; }
    
    .action-priority {
      font-size: 10px; font-weight: 800; text-transform: uppercase;
      letter-spacing: 0.5px; white-space: nowrap;
      padding: 3px 10px; border-radius: 12px;
    }
    .action-item.immediate  .action-priority { background: #e11d48; color: #fff; }
    .action-item.short-term .action-priority { background: #d97706; color: #fff; }
    .action-item.follow-up  .action-priority { background: #0284c7; color: #fff; }
    .action-text { font-size: 13px; color: #1e293b; font-weight: 600; }

    .footer {
      text-align: center; font-size: 12px; color: #94a3b8;
      margin-top: 60px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-weight: 500;
    }

    /* Sales Intelligence Styles */
    .si-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 24px;
    }
    .si-card {
      background: #ffffff;
      border-radius: 12px;
      border: 1px solid #e2e8f0;
      padding: 24px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }
    .si-card-title {
      font-size: 13px; font-weight: 700; color: #0f172a;
      margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
      text-transform: uppercase; letter-spacing: 0.5px;
      border-bottom: 1px solid #f1f5f9; padding-bottom: 8px;
    }
    .si-item { margin-bottom: 14px; }
    .si-item:last-child { margin-bottom: 0; }
    .si-label { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .si-value { font-size: 13px; color: #334155; line-height: 1.5; font-weight: 500; }
    .si-ts {
      font-size: 10px; font-weight: 700; color: #1e3a8a;
      background: #eff6ff; padding: 2px 6px; border-radius: 4px;
      margin-left: 6px; vertical-align: middle;
    }

    /* Overall Score & Pitch Coverage Dashboard Fixes */
    .overall-score-grid {
      display: flex; gap: 48px; align-items: center; flex-wrap: wrap;
    }
    @media (max-width: 768px) { .overall-score-grid { gap: 28px; } }

    .donut-wrapper { flex-shrink: 0; display: flex; justify-content: center; width: 140px; }
    .donut-chart {
      width: 130px; height: 130px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      box-shadow: inset 0 0 0 2px #f1f5f9;
    }
    .donut-inner {
      width: 104px; height: 104px; background: #fff; border-radius: 50%;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .donut-score { font-size: 36px; font-weight: 800; color: #0f172a; line-height: 1; letter-spacing: -1px; }
    .donut-max { font-size: 12px; color: #94a3b8; font-weight: 700; margin-top: 2px; }
    
    .score-breakdown { flex-grow: 1; min-width: 300px; display: flex; flex-direction: column; gap: 14px; }
    .breakdown-title { font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
    .breakdown-row { display: flex; align-items: center; gap: 16px; }
    .breakdown-label { width: 160px; font-size: 13px; color: #475569; font-weight: 600; }
    .breakdown-bar-bg { flex-grow: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
    .breakdown-bar-fill { height: 100%; border-radius: 4px; }
    .fill-compliance { background: #10b981; }
    .fill-pitch { background: #f59e0b; }
    .fill-sales { background: #3b82f6; }
    .breakdown-val { width: 60px; text-align: right; font-size: 13px; font-weight: 700; color: #0f172a; }
    
    .grade-badge {
      display: inline-block; padding: 6px 16px; border-radius: 20px;
      font-size: 12px; font-weight: 700; color: #b45309; background: #fef3c7;
      margin-top: 12px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .deductions-text { font-size: 13px; color: #64748b; line-height: 1.6; font-weight: 500; margin-top: 4px; }

    .pitch-map-header { margin-bottom: 32px; background: #f8fafc; padding: 20px 24px; border-radius: 10px; border: 1px solid #f1f5f9; }
    .pitch-map-title { font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
    .pitch-overall-bar-bg { width: 100%; height: 12px; background: #e2e8f0; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }
    .pitch-overall-bar-fill { height: 100%; background: #1e3a8a; border-radius: 6px; }
    .pitch-overall-stats { display: flex; justify-content: space-between; font-size: 12px; color: #475569; font-weight: 700; }
    
    .pitch-steps-container { position: relative; padding-left: 8px; }
    /* Modern vertical timeline guide line */
    .pitch-steps-container::before {
      content: ''; position: absolute; left: 23px; top: 16px; bottom: 16px;
      width: 2px; background: #e2e8f0; z-index: 1;
    }
    
    .pitch-step { display: flex; gap: 20px; margin-bottom: 24px; position: relative; z-index: 2; }
    .pitch-step:last-child { margin-bottom: 0; }
    .pitch-step-icon {
      width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px; font-weight: 700; color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .icon-covered { background: #10b981; }
    .icon-partial { background: #f59e0b; }
    .icon-skipped { background: #ef4444; }
    
    .pitch-step-content { flex-grow: 1; background: #f8fafc; padding: 14px 20px; border-radius: 8px; border: 1px solid #f1f5f9; }
    .pitch-step-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; flex-wrap: wrap; }
    .pitch-step-name { font-size: 14px; font-weight: 700; color: #0f172a; }
    .pitch-step-badge { font-size: 10px; font-weight: 800; padding: 3px 10px; border-radius: 12px; text-transform: uppercase; letter-spacing: 0.3px; }
    .badge-covered { background: #dcfce7; color: #15803d; }
    .badge-partial { background: #fef3c7; color: #b45309; }
    .badge-skipped { background: #fee2e2; color: #b91c1c; }
    .pitch-step-ts { font-size: 11px; color: #2563eb; font-weight: 700; background: #eff6ff; padding: 2px 8px; border-radius: 6px; }
    .pitch-step-reason { font-size: 13px; color: #475569; line-height: 1.6; font-weight: 500; }
"""


def fmt_null(value, fallback="—"):
    if value is None:
        return f'<span class="meta-value null-val">{fallback}</span>'
    return f'<span class="meta-value">{escape(str(value))}</span>'


def render_header(d, report):
    flagged = d.get("call_flagged", False)
    flag_class = "flagged" if flagged else "clean"
    flag_icon = "&#9888;" if flagged else "&#10003;"
    flag_text = "Call Flagged" if flagged else "No Incidents"

    sev = d.get("highest_severity", "None") or "None"
    sev_label = SEV_LABELS.get(sev, sev)
    sev_cls = SEV_BADGE_CLASS.get(sev, "sev-None")

    course = escape(d.get("course_name", ""))
    institute = escape(d.get("course_institute", ""))
    analysis_date = escape(report.get("analysis_date", ""))

    return f"""
  <div class="header">
    <div class="header-left">
      <h1>Call Quality Report</h1>
      <div class="subtitle">{course} &nbsp;&middot;&nbsp; {institute} &nbsp;&middot;&nbsp; {analysis_date}</div>
    </div>
    <div class="header-meta">
      <span class="flag-badge {flag_class}">{flag_icon} {flag_text}</span>
      <span class="severity-badge {sev_cls}">Highest: {sev} &mdash; {sev_label}</span>
    </div>
  </div>"""


def render_call_info(d, report):
    stt = d.get("call_stt_file")
    stt_display = os.path.basename(stt) if stt else None

    rows = [
        ("Call ID", d.get("call_id")),
        ("Sales Rep", d.get("sales_rep_name")),
        ("Rep ID", d.get("sales_rep_id")),
        ("Customer", d.get("customer_name")),
        ("Course", d.get("course_name")),
        ("Institute", d.get("course_institute")),
        ("STT File", stt_display),
        ("Recording File", d.get("call_recording_file")),
        ("Analysis Date", report.get("analysis_date")),
    ]

    items = ""
    for label, value in rows:
        items += f"""
        <div class="meta-item">
          <span class="meta-label">{escape(label)}</span>
          {fmt_null(value)}
        </div>"""

    return f"""
  <div class="section">
    <div class="section-title">Call Information</div>
    <div class="card">
      <div class="meta-grid">{items}
      </div>
    </div>
  </div>"""


def render_statistics(d, stats):
    rep_ratio = stats.get("rep_talk_ratio_pct", 0)
    cust_ratio = round(100 - rep_ratio, 1)
    total_utterances = stats.get("sales_rep_utterances", 0) + stats.get("customer_utterances", 0)

    def fmt_num(n):
        return f"{n:,}" if isinstance(n, int) else str(n)

    return f"""
  <div class="section">
    <div class="section-title">Call Statistics</div>
    <div class="stats-grid">
      <div class="stat-card">
        <span class="stat-label">Duration</span>
        <span class="stat-value">{escape(d.get("call_duration", ""))}</span>
        <span class="stat-sub">{stats.get("duration_seconds", 0)} seconds</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Words</span>
        <span class="stat-value">{fmt_num(stats.get("total_words", 0))}</span>
        <span class="stat-sub">Rep: {fmt_num(stats.get("rep_words", 0))} &nbsp;/&nbsp; Cust: {fmt_num(stats.get("customer_words", 0))}</span>
        <div class="ratio-bar-wrap">
          <div class="ratio-bar">
            <div class="ratio-rep" style="width:{rep_ratio}%"></div>
            <div class="ratio-cust" style="width:{cust_ratio}%"></div>
          </div>
          <div class="ratio-legend">
            <span><span class="legend-dot" style="background:#1e3a8a"></span>Rep {rep_ratio}%</span>
            <span><span class="legend-dot" style="background:#38bdf8"></span>Cust {cust_ratio}%</span>
          </div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-label">Utterances</span>
        <span class="stat-value">{total_utterances}</span>
        <span class="stat-sub">Rep: {stats.get("sales_rep_utterances", 0)} &nbsp;/&nbsp; Cust: {stats.get("customer_utterances", 0)}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Transcript Tokens</span>
        <span class="stat-value">{fmt_num(stats.get("transcript_tokens", stats.get("est_transcript_tokens", 0)))}</span>
        <span class="stat-sub">chars &divide; 4 estimate</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Input Tokens</span>
        <span class="stat-value">{fmt_num(stats.get("input_tokens", stats.get("est_input_tokens", 0)))}</span>
        <span class="stat-sub">actual prompt tokens</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Output Tokens</span>
        <span class="stat-value">{fmt_num(stats.get("output_tokens", stats.get("est_output_tokens", 0)))}</span>
        <span class="stat-sub">actual completion tokens</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Tokens</span>
        <span class="stat-value">{fmt_num(stats.get("total_tokens", stats.get("est_total_tokens", 0)))}</span>
        <span class="stat-sub">input + output</span>
      </div>
    </div>
  </div>"""


def render_incident_summary(summary):
    return f"""
  <div class="section">
    <div class="section-title">Incident Summary</div>
    <div class="card">
      <div class="summary-pills">
        <div class="pill l1">
          <span class="pill-count">{summary.get("L1", 0)}</span>
          <span class="pill-label">L1<br>Minor</span>
        </div>
        <div class="pill l2">
          <span class="pill-count">{summary.get("L2", 0)}</span>
          <span class="pill-label">L2<br>Major</span>
        </div>
        <div class="pill l3">
          <span class="pill-count">{summary.get("L3", 0)}</span>
          <span class="pill-label">L3<br>Critical</span>
        </div>
        <div class="pill total">
          <span class="pill-count">{summary.get("total", 0)}</span>
          <span class="pill-label">Total<br>Incidents</span>
        </div>
      </div>
    </div>
  </div>"""


def render_incidents(incidents):
    if not incidents:
        return """
  <div class="section">
    <div class="section-title">Incidents</div>
    <div class="card"><p style="color:#94a3b8;font-style:italic;font-weight:500;">No incidents detected.</p></div>
  </div>"""

    cards = ""
    for inc in incidents:
        sev = inc.get("severity", "L1")
        sev_label = SEV_LABELS.get(sev, sev)
        sev_cls = SEV_BADGE_CLASS.get(sev, "sev-L1")
        cards += f"""
    <div class="incident-card {sev_cls}">
      <div class="incident-header">
        <span class="incident-id">#{inc.get("id")}</span>
        <span class="severity-badge {sev_cls}">{sev} &mdash; {sev_label}</span>
        <span class="incident-category">{escape(inc.get("category", ""))}</span>
        <span class="incident-ts">{escape(inc.get("timestamp", ""))}</span>
      </div>
      <div class="incident-grid">
        <div class="incident-field">
          <span class="field-label">What Rep Said</span>
          <span class="field-value">{escape(inc.get("what_rep_said", ""))}</span>
        </div>
        <div class="incident-field">
          <span class="field-label">What Is Correct</span>
          <span class="field-value correct">{escape(inc.get("what_is_correct", ""))}</span>
        </div>
      </div>
      <div class="transcript-quote">{escape(inc.get("transcript_quote", ""))}</div>
      <div class="violation-basis">{escape(inc.get("violation_basis", ""))}</div>
    </div>"""

    return f"""
  <div class="section">
    <div class="section-title">Incidents</div>{cards}
  </div>"""


def render_checklist(checklist):
    if not checklist:
        return ""

    # Group by category
    categories = {}
    for item in checklist:
        cat = item.get("category", "Other")
        categories.setdefault(cat, []).append(item)

    rows = ""
    for cat, items in categories.items():
        rows += f"""
          <tr class="cat-header"><td colspan="3">{escape(cat)}</td></tr>"""
        for item in items:
            status = item.get("status", "")
            if status == "Pass":
                status_html = f'<span class="status-pass">&#10003; Pass</span>'
            elif status == "FAIL":
                status_html = f'<span class="status-fail">&#10007; FAIL</span>'
            else:
                status_html = f'<span class="status-nd">— Not discussed</span>'

            ref = item.get("incident_ref")
            ref_html = f'<span class="inc-ref-link">#{ref}</span>' if ref else ""
            rows += f"""
          <tr>
            <td>{escape(item.get("check", ""))}</td>
            <td>{status_html}</td>
            <td>{ref_html}</td>
          </tr>"""

    return f"""
  <div class="section">
    <div class="section-title">QA Checklist</div>
    <div class="card" style="padding:0;overflow:hidden">
      <table class="checklist-table">
        <thead>
          <tr>
            <th>Check</th>
            <th>Status</th>
            <th>Incident</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
  </div>"""


def render_assessment(text):
    return f"""
  <div class="section">
    <div class="section-title">Overall Assessment</div>
    <div class="card">
      <p class="assessment-text">{escape(text or "")}</p>
    </div>
  </div>"""


def render_recommended_action(rec_action):
    rule = rec_action.get("rule", "")
    actions = rec_action.get("actions", [])

    action_items = ""
    for act in actions:
        priority = act.get("priority", "Follow-up")
        cls = PRIORITY_CLASS.get(priority, "follow-up")
        action_items += f"""
        <div class="action-item {cls}">
          <span class="action-priority">{escape(priority)}</span>
          <span class="action-text">{escape(act.get("action", ""))}</span>
        </div>"""

    return f"""
  <div class="section">
    <div class="section-title">Recommended Action</div>
    <div class="card">
      <div class="rule-box">{escape(rule)}</div>
      <div class="action-list">{action_items}
      </div>
    </div>
  </div>"""


def render_sales_intelligence(si):
    if not si:
        return ""

    def get_val_ts(obj, key):
        item = obj.get(key, {})
        if isinstance(item, dict):
            val = item.get("value", "—")
            ts = item.get("timestamp")
        else:
            val = item or "—"
            ts = None
        ts_html = f'<span class="si-ts">{escape(ts)}</span>' if ts else ""
        return f"{escape(str(val))}{ts_html}"

    persona = si.get("customer_persona", {})
    psych = si.get("sales_psychology", {})
    lost = si.get("lost_opportunity", {})

    return f"""
  <div class="section">
    <div class="section-title">Sales Intelligence & Lost Opportunity Audit</div>
    <div class="si-grid">
      <div class="si-card">
        <div class="si-card-title">Customer Persona</div>
        <div class="si-item">
          <span class="si-label">Professional Context</span>
          <span class="si-value">{get_val_ts(persona, "professional_context")}</span>
        </div>
        <div class="si-item">
          <span class="si-label">Financial Baseline</span>
          <span class="si-value">{get_val_ts(persona, "financial_baseline")}</span>
        </div>
        <div class="si-item">
          <span class="si-label">Core Motivation</span>
          <span class="si-value">{get_val_ts(persona, "core_motivation")}</span>
        </div>
      </div>

      <div class="si-card">
        <div class="si-card-title">Sales Psychology</div>
        <div class="si-item">
          <span class="si-label">Consultative vs. Product-Push</span>
          <span class="si-value">{get_val_ts(psych, "consultative_vs_product_push")}</span>
        </div>
        <div class="si-item">
          <span class="si-label">Hype Authenticity</span>
          <span class="si-value">{get_val_ts(psych, "hype_authenticity")}</span>
        </div>
        <div class="si-item">
          <span class="si-label">Tone/Energy</span>
          <span class="si-value">{get_val_ts(psych, "tone_energy")}</span>
        </div>
      </div>

      <div class="si-card">
        <div class="si-card-title">Lost Opportunity Analysis</div>
        <div class="si-item">
          <span class="si-label">Objection Handling</span>
          <span class="si-value">{get_val_ts(lost, "objection_handling")}</span>
        </div>
        <div class="si-item">
          <span class="si-label">The "Drop" Reason</span>
          <span class="si-value">{get_val_ts(lost, "drop_reason")}</span>
        </div>
      </div>
    </div>
  </div>"""


def render_overall_call_score(overall_call_score: dict) -> str:
    if not overall_call_score:
        return ""

    total = overall_call_score.get("total_score", 0)
    c_score = overall_call_score.get("compliance_score", 0)
    p_score = overall_call_score.get("pitch_coverage_score", 0)
    s_score = overall_call_score.get("sales_quality_score", 0)
    grade = overall_call_score.get("grade", "")
    deductions = overall_call_score.get("deductions_text", "")

    # Calculate percentages for the bars
    c_pct = min(100, (c_score / 35) * 100) if c_score else 0
    p_pct = min(100, (p_score / 30) * 100) if p_score else 0
    s_pct = min(100, (s_score / 35) * 100) if s_score else 0

    return f"""
  <div class="section">
    <div class="section-title">Overall Call Score</div>
    <div class="card">
      <div class="overall-score-grid">
        <div class="donut-wrapper">
          <div class="donut-chart" style="background: conic-gradient(#f59e0b 0% {total}%, #f1f5f9 {total}% 100%);">
            <div class="donut-inner">
              <span class="donut-score">{total}</span>
              <span class="donut-max">/100</span>
            </div>
          </div>
        </div>
        <div class="score-breakdown">
          <div class="breakdown-title">Score Breakdown</div>
          
          <div class="breakdown-row">
            <span class="breakdown-label">Compliance (&times;35)</span>
            <div class="breakdown-bar-bg">
              <div class="breakdown-bar-fill fill-compliance" style="width: {c_pct}%;"></div>
            </div>
            <span class="breakdown-val">{c_score} / 35</span>
          </div>

          <div class="breakdown-row">
            <span class="breakdown-label">Pitch Coverage (&times;30)</span>
            <div class="breakdown-bar-bg">
              <div class="breakdown-bar-fill fill-pitch" style="width: {p_pct}%;"></div>
            </div>
            <span class="breakdown-val">{p_score} / 30</span>
          </div>

          <div class="breakdown-row">
            <span class="breakdown-label">Sales Quality (&times;35)</span>
            <div class="breakdown-bar-bg">
              <div class="breakdown-bar-fill fill-sales" style="width: {s_pct}%;"></div>
            </div>
            <span class="breakdown-val">{s_score} / 35</span>
          </div>
          
          <div style="margin-top: 4px;">
            <span class="grade-badge">{escape(grade)}</span>
            <div class="deductions-text">{escape(deductions)}</div>
          </div>
        </div>
      </div>
    </div>
  </div>"""


def render_sales_pitch_coverage(pitch_coverage: dict) -> str:
    if not pitch_coverage:
        return ""

    overall_pct = pitch_coverage.get("overall_coverage_pct", 0)
    steps_covered = pitch_coverage.get("steps_covered", 0)
    total_steps = pitch_coverage.get("total_steps", 0)
    steps = pitch_coverage.get("steps", [])

    step_html = ""
    for s in steps:
        status = s.get("status", "SKIPPED").upper()
        if status == "COVERED":
            icon = "&#10003;"
            icon_cls = "icon-covered"
            badge_cls = "badge-covered"
        elif status == "PARTIAL":
            icon = "~"
            icon_cls = "icon-partial"
            badge_cls = "badge-partial"
        else:
            icon = "&#10007;"
            icon_cls = "icon-skipped"
            badge_cls = "badge-skipped"

        ts = s.get("timestamp_range")
        ts_html = f'<span class="pitch-step-ts">{escape(ts)}</span>' if ts else ""

        step_html += f"""
        <div class="pitch-step">
          <div class="pitch-step-icon {icon_cls}">{icon}</div>
          <div class="pitch-step-content">
            <div class="pitch-step-title-row">
              <span class="pitch-step-name">{escape(s.get("step_title", ""))}</span>
              <span class="pitch-step-badge {badge_cls}">{status}</span>
              {ts_html}
            </div>
            <div class="pitch-step-reason">{escape(s.get("reasoning", ""))}</div>
          </div>
        </div>"""

    return f"""
  <div class="section">
    <div class="section-title">Sales Pitch Coverage Map</div>
    <div class="card">
      <div class="pitch-map-header">
        <div class="pitch-map-title">Overall Pitch Coverage Score</div>
        <div class="pitch-overall-bar-bg">
          <div class="pitch-overall-bar-fill" style="width: {overall_pct}%;"></div>
        </div>
        <div class="pitch-overall-stats">
          <span>0%</span>
          <span>{overall_pct}% ({steps_covered} / {total_steps} steps)</span>
          <span>100%</span>
        </div>
      </div>
      <div class="pitch-steps-container">
        {step_html}
      </div>
    </div>
  </div>"""


def generate_html(data: dict) -> str:
    report = data.get("report", {})
    stats = report.get("call_statistics", {})
    rep_name = data.get("sales_rep_name", "Rep")
    customer = data.get("customer_name", "Customer")
    title = f"Call Quality Report &mdash; {escape(rep_name)} / {escape(customer)}"

    # ------------------------------------------------------------------
    # Tab 1 — Incident Report
    # Every existing section, in the existing order. This includes the
    # Sales Pitch score (`overall_call_score`) and its coverage map, which
    # render only when a Sales Pitch was uploaded. Nothing here changed.
    # ------------------------------------------------------------------
    incident_parts = [
        render_call_info(data, report),
        render_statistics(data, stats),
        render_overall_call_score(report.get("overall_call_score")),
        render_sales_pitch_coverage(report.get("sales_pitch_coverage")),
        render_incident_summary(report.get("incident_summary", {})),
        render_incidents(report.get("incidents", [])),
        render_checklist(report.get("checklist", [])),
        render_assessment(report.get("overall_assessment", "")),
    ]

    rec_action = report.get("recommended_action")
    if rec_action:
        incident_parts.append(render_recommended_action(rec_action))

    incident_parts.append(render_sales_intelligence(report.get("sales_intelligence")))
    incident_html = "\n".join(incident_parts)

    # ------------------------------------------------------------------
    # Tab 2 — Rubric Report
    # `rubric_assessment` is written by assessment_service and is entirely
    # separate from `overall_call_score` above. When the methodology pass
    # fails it is None, the tab is omitted, and render_tabs falls back to a
    # single-tab shell that looks identical to the previous report.
    # ------------------------------------------------------------------
    incidents = report.get("incidents") or []
    panels = [("incident", "Incident Report", incident_html)]
    badges = {"incident": str(len(incidents)) if incidents else "Clean"}

    rubric = report.get("rubric_assessment")
    if rubric and rubric.get("_methodology"):
        panels.append(
            ("rubric", "Rubric Report", render_methodology_section(rubric, CHAPTERS))
        )
        badges["rubric"] = str(rubric.get("total_score", "—"))

    # Header and footer sit OUTSIDE the tab shell so call metadata stays
    # visible on both tabs.
    body = "\n".join([
        render_header(data, report),
        render_tabs(panels, badges=badges),
        '  <div class="footer">Generated by Call Quality Agent '
        '&nbsp;&middot;&nbsp; Accredian</div>',
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>{CSS}
{tabs_css()}
{methodology_css()}
  </style>
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python src/report_html.py <report_json_path>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    stem = os.path.splitext(json_path)[0]
    if not stem.endswith(".report"):
        stem = stem + ".report"
    html_path = stem + ".html"

    html = generate_html(data)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML report written to: {html_path}")


if __name__ == "__main__":
    main()