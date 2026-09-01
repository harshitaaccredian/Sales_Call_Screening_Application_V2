# """
# HTML renderer for the Sales Methodology Adherence section.

# Self-contained: `methodology_css()` returns a <style> block scoped with an
# `mth-` prefix so it can be appended to the existing report stylesheet without
# collisions. Design tokens are taken from the existing report (slate palette,
# #2563eb accent, 10px card radius) so the new section reads as part of the
# same document rather than a bolt-on.

# The signature element is the Trust Journey rail: five sequential stages with
# the stall point marked. It is the one place the section spends visual weight,
# because "how far did trust actually get" is the question a sales manager
# opens the report to answer.

# Usage
# -----
#     from src.report_methodology import methodology_css, render_methodology_section

#     html = render_methodology_section(score_obj)   # output of compute_overall_score
# """

# from __future__ import annotations

# import html as _html
# from typing import Any

# # =============================================================================
# # Design tokens — inherited from the existing report
# # =============================================================================

# BAND_STYLE = {
#     "great":   ("#10b981", "#d1fae5", "Great"),
#     "good":    ("#2563eb", "#dbeafe", "Good"),
#     "average": ("#f59e0b", "#fef3c7", "Average"),
#     "missing": ("#ef4444", "#fee2e2", "Missing"),
# }

# STATUS_STYLE = {
#     "answered":            ("#10b981", "#d1fae5", "Answered"),
#     "partial":             ("#f59e0b", "#fef3c7", "Partial"),
#     "unanswered":          ("#ef4444", "#fee2e2", "Unanswered"),
#     "not_applicable":      ("#94a3b8", "#f1f5f9", "N/A"),
#     "addressed":           ("#10b981", "#d1fae5", "Addressed"),
#     "partially_addressed": ("#f59e0b", "#fef3c7", "Partial"),
#     "not_addressed":       ("#ef4444", "#fee2e2", "Not addressed"),
# }

# TRUST_STAGES = [
#     ("hear_me",      "Hear Me",       "You understand what I am saying."),
#     ("understand_me", "Understand Me", "You understand my situation."),
#     ("guide_me",     "Guide Me",      "Your recommendation fits my needs."),
#     ("reassure_me",  "Reassure Me",   "My concerns have been addressed."),
#     ("i_ll_decide",  "I'll Decide",   "I am ready to move forward."),
# ]

# WHY_LABELS = {
#     "why_change":    "Why Change?",
#     "why_now":       "Why Now?",
#     "why_accredian": "Why Accredian?",
#     "why_you":       "Why You?",
# }

# HFTE_LABELS = {"hope": "Hope", "fear": "Fear", "trust": "Trust", "effort": "Effort"}


# def e(v: Any) -> str:
#     return _html.escape(str(v if v is not None else ""), quote=True)


# # =============================================================================
# # CSS
# # =============================================================================

# def methodology_css() -> str:
#     return """
#     /* ---- Sales Methodology section ---- */
#     .mth-scorebar-wrap { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
#     .mth-scorebar-label { font-size: 13px; font-weight: 700; color: #0f172a; min-width: 210px; }
#     .mth-scorebar-bg { flex-grow: 1; height: 10px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }
#     .mth-scorebar-fill { height: 100%; border-radius: 5px; }
#     .mth-scorebar-pts { font-size: 12px; font-weight: 700; color: #475569; min-width: 74px; text-align: right; }

#     .mth-band { font-size: 10px; font-weight: 800; padding: 3px 10px; border-radius: 12px;
#                 text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; }

#     .mth-dim { border: 1px solid #f1f5f9; border-radius: 10px; padding: 18px 22px;
#                margin-bottom: 14px; background: #fff; }
#     .mth-dim-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
#     .mth-dim-name { font-size: 15px; font-weight: 700; color: #0f172a; }
#     .mth-dim-chapter { font-size: 11px; color: #94a3b8; font-weight: 600; }
#     .mth-dim-pts { margin-left: auto; font-size: 12px; font-weight: 800; color: #475569; }
#     .mth-dim-reason { font-size: 13px; color: #475569; line-height: 1.65; margin: 8px 0 12px; }

#     .mth-quote { border-left: 3px solid #cbd5e1; background: #f8fafc; padding: 9px 14px;
#                  margin: 6px 0; border-radius: 0 6px 6px 0; font-size: 12.5px;
#                  color: #334155; font-style: italic; }
#     .mth-quote-ts { font-style: normal; font-weight: 700; color: #2563eb; font-size: 11px;
#                     background: #eff6ff; padding: 1px 7px; border-radius: 5px; margin-right: 8px; }

#     .mth-miss { border-left: 3px solid #f59e0b; background: #fffbeb; padding: 12px 16px;
#                 margin: 8px 0; border-radius: 0 6px 6px 0; }
#     .mth-miss-head { font-size: 11px; font-weight: 800; color: #b45309;
#                      text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 6px; }
#     .mth-miss-row { font-size: 12.5px; color: #475569; line-height: 1.6; margin-bottom: 4px; }
#     .mth-miss-row b { color: #0f172a; font-weight: 700; }
#     .mth-miss-better { background: #ecfdf5; border-radius: 6px; padding: 8px 12px; margin-top: 8px;
#                        font-size: 12.5px; color: #065f46; line-height: 1.6; }

#     /* ---- Trust Journey rail (signature element) ---- */
#     .mth-trust { background: #0f172a; border-radius: 12px; padding: 26px 28px 22px; margin-bottom: 24px; }
#     .mth-trust-title { font-size: 11px; font-weight: 800; color: #64748b;
#                        text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 20px; }
#     .mth-rail { display: flex; align-items: flex-start; gap: 0; }
#     .mth-stage { flex: 1; position: relative; text-align: center; padding: 0 4px; }
#     .mth-stage::before { content: ""; position: absolute; top: 13px; left: -50%;
#                          width: 100%; height: 2px; background: #1e293b; z-index: 1; }
#     .mth-stage:first-child::before { display: none; }
#     .mth-stage.reached::before { background: #10b981; }
#     .mth-stage-dot { position: relative; z-index: 2; width: 28px; height: 28px; border-radius: 50%;
#                      margin: 0 auto 10px; display: flex; align-items: center; justify-content: center;
#                      font-size: 12px; font-weight: 800; background: #1e293b; color: #475569;
#                      border: 2px solid #1e293b; }
#     .mth-stage.reached .mth-stage-dot { background: #10b981; color: #052e16; border-color: #10b981; }
#     .mth-stage.stall .mth-stage-dot { background: #0f172a; color: #f59e0b; border-color: #f59e0b; }
#     .mth-stage-name { font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 3px; }
#     .mth-stage.reached .mth-stage-name { color: #f8fafc; }
#     .mth-stage.stall .mth-stage-name { color: #f59e0b; }
#     .mth-stage-feel { font-size: 10.5px; color: #475569; line-height: 1.45; }
#     .mth-stage.reached .mth-stage-feel { color: #94a3b8; }
#     .mth-stall-note { margin-top: 20px; padding-top: 16px; border-top: 1px solid #1e293b;
#                       font-size: 12.5px; color: #cbd5e1; line-height: 1.6; }
#     .mth-stall-note b { color: #f59e0b; font-weight: 700; }

#     /* ---- Diagnostics grids ---- */
#     .mth-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
#     .mth-cell { border: 1px solid #f1f5f9; border-radius: 8px; padding: 13px 16px; background: #fff; }
#     .mth-cell-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 5px; }
#     .mth-cell-label { font-size: 13px; font-weight: 700; color: #0f172a; }
#     .mth-cell-note { font-size: 12px; color: #64748b; line-height: 1.55; }

#     .mth-hfte { display: flex; align-items: stretch; gap: 14px; flex-wrap: wrap; }
#     .mth-hfte-side { flex: 1; min-width: 240px; border-radius: 10px; padding: 16px 18px; }
#     .mth-hfte-side.pos { background: #f0fdf4; border: 1px solid #dcfce7; }
#     .mth-hfte-side.neg { background: #fef2f2; border: 1px solid #fee2e2; }
#     .mth-hfte-title { font-size: 11px; font-weight: 800; text-transform: uppercase;
#                       letter-spacing: 0.4px; margin-bottom: 10px; }
#     .mth-hfte-side.pos .mth-hfte-title { color: #15803d; }
#     .mth-hfte-side.neg .mth-hfte-title { color: #b91c1c; }

#     .mth-na { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
#               background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;
#               padding: 12px 16px; margin-bottom: 18px; }
#     .mth-na-label { font-size: 11px; font-weight: 800; color: #64748b;
#                     text-transform: uppercase; letter-spacing: 0.4px; }
#     .mth-na-chip { font-size: 11.5px; font-weight: 600; color: #475569;
#                    background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 3px 11px; }

#     .mth-coach { background: #eff6ff; border: 1px solid #dbeafe; border-radius: 10px;
#                  padding: 20px 24px; margin-top: 6px; }
#     .mth-coach-row { display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; }
#     .mth-coach-row:last-child { margin-bottom: 0; }
#     .mth-coach-key { font-size: 11px; font-weight: 800; color: #1e40af; text-transform: uppercase;
#                      letter-spacing: 0.4px; min-width: 128px; padding-top: 2px; }
#     .mth-coach-val { font-size: 13px; color: #1e3a8a; line-height: 1.65; flex: 1; }

#     /* ---- Verbose scorecard table ---- */
#     .mth-sc { width: 100%; border-collapse: collapse; font-size: 13px; }
#     .mth-sc thead th {
#       text-align: left; font-size: 10.5px; font-weight: 800; color: #94a3b8;
#       text-transform: uppercase; letter-spacing: .5px;
#       padding: 0 14px 10px; border-bottom: 1px solid #e2e8f0;
#     }
#     .mth-sc tbody td { padding: 15px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
#     .mth-sc tbody tr:last-child td { border-bottom: none; }
#     .mth-sc-name { font-weight: 700; color: #0f172a; white-space: nowrap; }
#     .mth-sc-ch { display: block; font-size: 11px; color: #94a3b8; font-weight: 600; margin-top: 3px; }
#     .mth-sc-pts { font-weight: 800; color: #0f172a; white-space: nowrap; text-align: right; }
#     .mth-sc-den { font-size: 11px; font-weight: 700; color: #94a3b8; }
#     .mth-sc-wt { display: block; font-size: 10.5px; font-weight: 700; color: #94a3b8;
#                  margin-top: 3px; letter-spacing: .2px; }
#     .mth-sc-obs { color: #475569; line-height: 1.65; }
#     .mth-sc-na td { background: #f8fafc; color: #94a3b8; }
#     .mth-sc-count { font-size: 11px; font-weight: 700; color: #64748b;
#                     background: #f1f5f9; padding: 3px 11px; border-radius: 11px; }

#     .mth-warn { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
#                 padding: 12px 16px; margin-bottom: 18px; font-size: 12.5px; color: #92400e; line-height: 1.6; }

#     @media (max-width: 720px) {
#       .mth-rail { flex-direction: column; gap: 14px; }
#       .mth-stage { text-align: left; display: flex; gap: 12px; align-items: flex-start; }
#       .mth-stage::before { display: none; }
#       .mth-stage-dot { margin: 0; flex-shrink: 0; }
#       .mth-scorebar-wrap { flex-wrap: wrap; }
#       .mth-scorebar-label { min-width: 100%; }
#     }
#     """


# # =============================================================================
# # Fragments
# # =============================================================================

# def _band_chip(band: str) -> str:
#     color, bg, label = BAND_STYLE.get(band, BAND_STYLE["missing"])
#     return f'<span class="mth-band" style="background:{bg};color:{color}">{e(label)}</span>'


# def _status_chip(status: str) -> str:
#     color, bg, label = STATUS_STYLE.get(status, STATUS_STYLE["not_applicable"])
#     return f'<span class="mth-band" style="background:{bg};color:{color}">{e(label)}</span>'


# def _score_bar(label: str, score: float, maximum: float, color: str) -> str:
#     pct = round(100 * score / maximum) if maximum else 0
#     return f"""
#       <div class="mth-scorebar-wrap">
#         <span class="mth-scorebar-label">{e(label)}</span>
#         <div class="mth-scorebar-bg"><div class="mth-scorebar-fill"
#              style="width:{pct}%;background:{color}"></div></div>
#         <span class="mth-scorebar-pts">{score:.0f} / {maximum:.0f}</span>
#       </div>"""


# def _trust_rail(tj: dict) -> str:
#     reached = {s["id"] for s in tj.get("stages", []) if s.get("reached")}
#     furthest = tj.get("furthest_stage_reached")
#     notes = {s["id"]: s for s in tj.get("stages", [])}

#     cells = []
#     for idx, (sid, name, feeling) in enumerate(TRUST_STAGES, start=1):
#         is_reached = sid in reached
#         is_stall = sid == furthest
#         cls = "mth-stage" + (" reached" if is_reached else "") + (" stall" if is_stall else "")
#         mark = "&#10003;" if is_reached and not is_stall else str(idx)
#         note = notes.get(sid, {}).get("note") or feeling
#         cells.append(f"""
#         <div class="{cls}">
#           <div class="mth-stage-dot">{mark}</div>
#           <div>
#             <div class="mth-stage-name">{e(name)}</div>
#             <div class="mth-stage-feel">{e(note)}</div>
#           </div>
#         </div>""")

#     stall = tj.get("where_it_stalled")
#     stall_html = ""
#     if stall:
#         label = next((n for i, n, _ in TRUST_STAGES if i == furthest), furthest or "the start")
#         stall_html = (f'<div class="mth-stall-note">Conversation stalled at '
#                       f'<b>{e(label)}</b> &mdash; {e(stall)}</div>')
#     else:
#         stall_html = ('<div class="mth-stall-note">Reached <b>I\'ll Decide</b> '
#                       '&mdash; the full trust journey was completed.</div>')

#     return f"""
#     <div class="mth-trust">
#       <div class="mth-trust-title">Trust Journey &mdash; how far confidence actually travelled</div>
#       <div class="mth-rail">{''.join(cells)}</div>
#       {stall_html}
#     </div>"""


# def _trust_rail_section(tj: dict) -> str:
#     return f'''
#   <div class="section">
#     <div class="section-title">Trust Journey</div>
#     {_trust_rail(tj)}
#   </div>'''


# def _dimension(d: dict, chapters: dict[str, str]) -> str:
#     color = BAND_STYLE.get(d["band"], BAND_STYLE["missing"])[0]

#     quotes = "".join(
#         f'<div class="mth-quote"><span class="mth-quote-ts">{e(q.get("timestamp"))}</span>'
#         f'{e(q.get("quote"))}</div>'
#         for q in d.get("evidence", [])
#     )

#     misses = ""
#     for m in d.get("missed_opportunities", []) or []:
#         better = (f'<div class="mth-miss-better"><b>Try:</b> &ldquo;{e(m["better_response"])}&rdquo;</div>'
#                   if m.get("better_response") else "")
#         misses += f"""
#         <div class="mth-miss">
#           <div class="mth-miss-head">Missed opportunity &middot; {e(m.get('timestamp'))}</div>
#           <div class="mth-miss-row"><b>What happened:</b> {e(m.get('what_happened'))}</div>
#           <div class="mth-miss-row"><b>The Bible says:</b> {e(m.get('bible_says'))}</div>
#           {better}
#         </div>"""

#     return f"""
#     <div class="mth-dim">
#       <div class="mth-dim-head">
#         <span class="mth-dim-name">{e(d['name'])}</span>
#         {_band_chip(d['band'])}
#         <span class="mth-dim-chapter">{e(chapters.get(d['id'], ''))}</span>
#         <span class="mth-dim-pts">{d.get('out_of_ten', 0):.1f} / 10
#           <span style="color:#94a3b8;font-weight:600">&middot; weight {d.get('weight', 0):.0f}%</span></span>
#       </div>
#       <div class="mth-scorebar-bg" style="margin-bottom:10px">
#         <div class="mth-scorebar-fill" style="width:{d['pct']:.0f}%;background:{color}"></div>
#       </div>
#       <div class="mth-dim-reason">{e(d.get('reasoning'))}</div>
#       {quotes}
#       {misses}
#     </div>"""


# def _scorecard(meth: dict, chapters: dict[str, str]) -> str:
#     """Dense criteria/score/observations table.

#     Sits above the per-dimension detail so a manager can read the whole call in
#     one screen, then drill into evidence only where the score warrants it.
#     """
#     rows = ""
#     for d in meth.get("dimensions", []):
#         color = BAND_STYLE.get(d["band"], BAND_STYLE["missing"])[0]
#         rows += f"""
#         <tr>
#           <td class="mth-sc-name">{e(d['name'])}
#             <span class="mth-sc-ch">{e(chapters.get(d['id'], ''))}</span></td>
#           <td style="width:1%">{_band_chip(d['band'])}</td>
#           <td class="mth-sc-pts" style="width:1%;color:{color}">
#             {d.get('out_of_ten', 0):.1f}<span class="mth-sc-den"> / 10</span>
#             <span class="mth-sc-wt">weight {d.get('weight', 0):.0f}%</span></td>
#           <td class="mth-sc-obs">{e(d.get('reasoning'))}</td>
#         </tr>"""

#     for na in meth.get("not_applicable", []):
#         rows += f"""
#         <tr class="mth-sc-na">
#           <td class="mth-sc-name" style="color:#94a3b8">{e(na['name'])}
#             <span class="mth-sc-ch">{e(chapters.get(na['id'], ''))}</span></td>
#           <td style="width:1%">{_status_chip('not_applicable')}</td>
#           <td class="mth-sc-pts" style="width:1%;color:#cbd5e1">&mdash;
#             <span class="mth-sc-wt">excluded</span></td>
#           <td class="mth-sc-obs" style="color:#94a3b8">
#             Stage not reached on this call. Excluded from scoring; the remaining
#             weights are renormalised so the call is not penalised for it.</td>
#         </tr>"""

#     n = len(meth.get("dimensions", []))
#     return f"""
#     <div class="section">
#       <div class="section-title" style="display:flex;align-items:center;
#            justify-content:space-between;gap:12px">
#         <span>Detailed Rubric Scorecard</span>
#         <span class="mth-sc-count">{n} criteria evaluated</span>
#       </div>
#       <div class="card" style="padding:22px 14px">
#         <table class="mth-sc">
#           <thead><tr>
#             <th>Evaluation Criteria</th><th>Band</th>
#             <th style="text-align:right">Score</th>
#             <th>Key Assessment &amp; Observations</th>
#           </tr></thead>
#           <tbody>{rows}</tbody>
#         </table>
#       </div>
#     </div>"""


# def _four_whys(items: list[dict]) -> str:
#     if not items:
#         return ""
#     cells = "".join(f"""
#       <div class="mth-cell">
#         <div class="mth-cell-head">
#           <span class="mth-cell-label">{e(WHY_LABELS.get(w.get('id'), w.get('id')))}</span>
#           {_status_chip(w.get('status', 'unanswered'))}
#         </div>
#         <div class="mth-cell-note">{e(w.get('note'))}</div>
#       </div>""" for w in items)
#     return f"""
#     <div class="section">
#       <div class="section-title">The 4 WHYs &mdash; questions the customer needed answered</div>
#       <div class="card"><div class="mth-grid">{cells}</div></div>
#     </div>"""


# def _hfte(items: list[dict]) -> str:
#     if not items:
#         return ""
#     by_id = {i.get("id"): i for i in items}

#     def side(ids: list[str], cls: str, title: str) -> str:
#         rows = ""
#         for i in ids:
#             it = by_id.get(i, {})
#             rows += f"""
#             <div class="mth-cell" style="margin-bottom:8px">
#               <div class="mth-cell-head">
#                 <span class="mth-cell-label">{e(HFTE_LABELS.get(i, i))}</span>
#                 {_status_chip(it.get('status', 'not_addressed'))}
#               </div>
#               <div class="mth-cell-note">{e(it.get('note'))}</div>
#             </div>"""
#         return f'<div class="mth-hfte-side {cls}"><div class="mth-hfte-title">{e(title)}</div>{rows}</div>'

#     return f"""
#     <div class="section">
#       <div class="section-title">HFTE Balance &mdash; Hope + Trust must outweigh Fear + Effort</div>
#       <div class="card">
#         <div class="mth-hfte">
#           {side(['hope', 'trust'], 'pos', 'Drivers toward a decision')}
#           {side(['fear', 'effort'], 'neg', 'Drivers against a decision')}
#         </div>
#       </div>
#     </div>"""


# # =============================================================================
# # Main renderer
# # =============================================================================

# def render_methodology_section(score: dict, chapters: dict[str, str] | None = None) -> str:
#     """Render the full section from the output of scoring.compute_overall_score."""
#     meth = score.get("_methodology", {})
#     comp = score.get("_compliance", {})
#     chapters = chapters or {}

#     # --- Score summary -------------------------------------------------------
#     # Titled "Sales Bible Rubric Score", NOT "Overall Call Score" — the latter
#     # is the pre-existing sales-pitch section and the two are independent
#     # measurements. Sharing a title would invite them to be read as one number.
#     bars = _score_bar("Compliance & Fact Accuracy",
#                       score["compliance_score"], score["compliance_max"], "#2563eb")
#     bars += _score_bar("Sales Bible Methodology",
#                        score["methodology_score"], score["methodology_max"], "#8b5cf6")

#     warnings = ""
#     if score.get("cap_reason"):
#         warnings += (f'<div class="mth-warn"><b>Score capped.</b> {e(score["cap_reason"])}. '
#                      f'Methodology strength does not offset a compliance breach.</div>')
#     if score.get("low_confidence"):
#         warnings += ('<div class="mth-warn"><b>Low confidence.</b> This call was short, '
#                      'one-sided, or reached too few stages for a reliable methodology read. '
#                      'Treat the score as indicative and review manually.</div>')

#     na = ""
#     if meth.get("not_applicable"):
#         chips = "".join(f'<span class="mth-na-chip">{e(x["name"])}</span>'
#                         for x in meth["not_applicable"])
#         na = (f'<div class="mth-na"><span class="mth-na-label">Stages not reached '
#               f'&mdash; excluded from scoring</span>{chips}</div>')

#     # --- Penalties -----------------------------------------------------------
#     pens = meth.get("penalties", {})
#     pen = pens.get("applied", [])
#     pen_html = ""
#     if pen:
#         rows = "".join(f'<div class="mth-miss-row">&minus;{p["points"]} &nbsp; {e(p["reason"])}</div>'
#                        for p in pen)
#         applied_total = pens.get("total", 0)
#         raw_total = pens.get("total_uncapped", applied_total)
#         # When the proportional cap bites, say so — otherwise a header reading
#         # "-1.2 total" above a list summing to -14 looks like an arithmetic bug.
#         if pens.get("proportionally_capped"):
#             head = (f"Behavioural penalties &mdash; &minus;{applied_total:.1f} applied "
#                     f"(of &minus;{raw_total:.0f} identified)")
#             note = ('<div class="mth-miss-row" style="margin-top:8px;font-size:11.5px;color:#94a3b8">'
#                     'Penalties are capped at a share of the points earned, so behaviour already '
#                     'reflected in the band ratings above is not deducted twice.</div>')
#         else:
#             head = f"Behavioural penalties &mdash; &minus;{applied_total:.1f} total"
#             note = ""
#         pen_html = f"""
#         <div class="mth-miss" style="border-left-color:#ef4444;background:#fef2f2">
#           <div class="mth-miss-head" style="color:#b91c1c">{head}</div>{rows}{note}
#         </div>"""

#     dims = "".join(_dimension(d, chapters) for d in meth.get("dimensions", []))

#     coach = score.get("coaching_summary") or meth.get("coaching_summary") or {}
#     coach_html = ""
#     if coach:
#         rows = ""
#         for key, label in (("top_strength", "Top strength"),
#                            ("top_priority", "Highest-leverage fix"),
#                            ("one_behaviour_to_practice", "Next 10 calls")):
#             if coach.get(key):
#                 rows += (f'<div class="mth-coach-row"><span class="mth-coach-key">{e(label)}</span>'
#                          f'<span class="mth-coach-val">{e(coach[key])}</span></div>')
#         coach_html = f"""
#         <div class="section">
#           <div class="section-title">Coaching Focus</div>
#           <div class="mth-coach">{rows}</div>
#         </div>"""

#     return f"""
#   <div class="section">
#     <div class="section-title">Sales Bible Rubric Score</div>
#     <div class="card">
#       {warnings}
#       <div style="display:flex;align-items:center;gap:32px;flex-wrap:wrap;margin-bottom:22px">
#         <div style="text-align:center;min-width:150px">
#           <div style="font-size:52px;font-weight:800;color:{e(score['grade_color'])};
#                       line-height:1;letter-spacing:-2px">{score['total_score']}</div>
#           <div style="font-size:12px;color:#94a3b8;font-weight:700;margin-top:4px">out of 100</div>
#           <div style="font-size:13px;font-weight:800;color:{e(score['grade_color'])};
#                       margin-top:8px">{e(score['grade'])}</div>
#         </div>
#         <div style="flex-grow:1;min-width:300px">{bars}</div>
#       </div>
#       <div style="font-size:12.5px;color:#64748b;line-height:1.65;border-top:1px solid #f1f5f9;
#                   padding-top:14px">{e(score.get('deductions_text'))}</div>
#       <div style="font-size:11px;color:#cbd5e1;margin-top:10px">
#         Rubric v{e(score.get('rubric_version'))} &middot; Scoring v{e(score.get('scoring_version'))}
#         &middot; Independent of the Sales Pitch score
#       </div>
#     </div>
#   </div>

#   {_trust_rail_section(meth.get('trust_journey', {}))}

#   {_scorecard(meth, chapters)}

#   <div class="section">
#     <div class="section-title">Evidence &amp; Coaching Detail</div>
#     {na}
#     {pen_html}
#     {dims}
#   </div>

#   {_four_whys(meth.get('four_whys', []))}
#   {_hfte(meth.get('hfte_balance', []))}
#   {coach_html}
# """

"""
HTML renderer for the Sales Methodology Adherence section.

Self-contained: `methodology_css()` returns a <style> block scoped with an
`mth-` prefix so it can be appended to the existing report stylesheet without
collisions. Design tokens are taken from the existing report (slate palette,
#2563eb accent, 10px card radius) so the new section reads as part of the
same document rather than a bolt-on.

The signature element is the Trust Journey rail: five sequential stages with
the stall point marked. It is the one place the section spends visual weight,
because "how far did trust actually get" is the question a sales manager
opens the report to answer.

Usage
-----
    from src.report_methodology import methodology_css, render_methodology_section

    html = render_methodology_section(score_obj)   # output of compute_overall_score
"""

from __future__ import annotations

import html as _html
from typing import Any

# =============================================================================
# Design tokens — inherited from the existing report
# =============================================================================

BAND_STYLE = {
    "great":   ("#10b981", "#d1fae5", "Great"),
    "good":    ("#2563eb", "#dbeafe", "Good"),
    "average": ("#f59e0b", "#fef3c7", "Average"),
    "missing": ("#ef4444", "#fee2e2", "Missing"),
}

STATUS_STYLE = {
    "answered":            ("#10b981", "#d1fae5", "Answered"),
    "partial":             ("#f59e0b", "#fef3c7", "Partial"),
    "unanswered":          ("#ef4444", "#fee2e2", "Unanswered"),
    "not_applicable":      ("#94a3b8", "#f1f5f9", "N/A"),
    "addressed":           ("#10b981", "#d1fae5", "Addressed"),
    "partially_addressed": ("#f59e0b", "#fef3c7", "Partial"),
    "not_addressed":       ("#ef4444", "#fee2e2", "Not addressed"),
}

TRUST_STAGES = [
    ("hear_me",      "Hear Me",       "You understand what I am saying."),
    ("understand_me", "Understand Me", "You understand my situation."),
    ("guide_me",     "Guide Me",      "Your recommendation fits my needs."),
    ("reassure_me",  "Reassure Me",   "My concerns have been addressed."),
    ("i_ll_decide",  "I'll Decide",   "I am ready to move forward."),
]

WHY_LABELS = {
    "why_change":    "Why Change?",
    "why_now":       "Why Now?",
    "why_accredian": "Why Accredian?",
    "why_you":       "Why You?",
}

HFTE_LABELS = {"hope": "Hope", "fear": "Fear", "trust": "Trust", "effort": "Effort"}


def e(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""), quote=True)


# =============================================================================
# CSS
# =============================================================================

def methodology_css() -> str:
    return """
    /* ---- Sales Methodology section ---- */
    .mth-scorebar-wrap { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
    .mth-scorebar-label { font-size: 13px; font-weight: 700; color: #0f172a; min-width: 210px; }
    .mth-scorebar-bg { flex-grow: 1; height: 10px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }
    .mth-scorebar-fill { height: 100%; border-radius: 5px; }
    .mth-scorebar-pts { font-size: 12px; font-weight: 700; color: #475569; min-width: 74px; text-align: right; }

    .mth-band { font-size: 10px; font-weight: 800; padding: 3px 10px; border-radius: 12px;
                text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; }

    .mth-dim { border: 1px solid #f1f5f9; border-radius: 10px; padding: 18px 22px;
               margin-bottom: 14px; background: #fff; }
    .mth-dim-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
    .mth-dim-name { font-size: 15px; font-weight: 700; color: #0f172a; }
    .mth-dim-chapter { font-size: 11px; color: #94a3b8; font-weight: 600; }
    .mth-dim-pts { margin-left: auto; font-size: 12px; font-weight: 800; color: #475569; }
    .mth-dim-reason { font-size: 13px; color: #475569; line-height: 1.65; margin: 8px 0 12px; }

    .mth-quote { border-left: 3px solid #cbd5e1; background: #f8fafc; padding: 9px 14px;
                 margin: 6px 0; border-radius: 0 6px 6px 0; font-size: 12.5px;
                 color: #334155; font-style: italic; }
    .mth-quote-ts { font-style: normal; font-weight: 700; color: #2563eb; font-size: 11px;
                    background: #eff6ff; padding: 1px 7px; border-radius: 5px; margin-right: 8px; }

    .mth-miss { border-left: 3px solid #f59e0b; background: #fffbeb; padding: 12px 16px;
                margin: 8px 0; border-radius: 0 6px 6px 0; }
    .mth-miss-head { font-size: 11px; font-weight: 800; color: #b45309;
                     text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 6px; }
    .mth-miss-row { font-size: 12.5px; color: #475569; line-height: 1.6; margin-bottom: 4px; }
    .mth-miss-row b { color: #0f172a; font-weight: 700; }
    .mth-miss-better { background: #ecfdf5; border-radius: 6px; padding: 8px 12px; margin-top: 8px;
                       font-size: 12.5px; color: #065f46; line-height: 1.6; }

    /* ---- Trust Journey rail (signature element) ---- */
    .mth-trust { background: #0f172a; border-radius: 12px; padding: 26px 28px 22px; margin-bottom: 24px; }
    .mth-trust-title { font-size: 11px; font-weight: 800; color: #64748b;
                       text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 20px; }
    .mth-rail { display: flex; align-items: flex-start; gap: 0; }
    .mth-stage { flex: 1; position: relative; text-align: center; padding: 0 4px; }
    .mth-stage::before { content: ""; position: absolute; top: 13px; left: -50%;
                         width: 100%; height: 2px; background: #1e293b; z-index: 1; }
    .mth-stage:first-child::before { display: none; }
    .mth-stage.reached::before { background: #10b981; }
    .mth-stage-dot { position: relative; z-index: 2; width: 28px; height: 28px; border-radius: 50%;
                     margin: 0 auto 10px; display: flex; align-items: center; justify-content: center;
                     font-size: 12px; font-weight: 800; background: #1e293b; color: #475569;
                     border: 2px solid #1e293b; }
    .mth-stage.reached .mth-stage-dot { background: #10b981; color: #052e16; border-color: #10b981; }
    .mth-stage.stall .mth-stage-dot { background: #0f172a; color: #f59e0b; border-color: #f59e0b; }
    .mth-stage-name { font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 3px; }
    .mth-stage.reached .mth-stage-name { color: #f8fafc; }
    .mth-stage.stall .mth-stage-name { color: #f59e0b; }
    .mth-stage-feel { font-size: 10.5px; color: #475569; line-height: 1.45; }
    .mth-stage.reached .mth-stage-feel { color: #94a3b8; }
    .mth-stall-note { margin-top: 20px; padding-top: 16px; border-top: 1px solid #1e293b;
                      font-size: 12.5px; color: #cbd5e1; line-height: 1.6; }
    .mth-stall-note b { color: #f59e0b; font-weight: 700; }

    /* ---- Diagnostics grids ---- */
    .mth-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .mth-cell { border: 1px solid #f1f5f9; border-radius: 8px; padding: 13px 16px; background: #fff; }
    .mth-cell-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 5px; }
    .mth-cell-label { font-size: 13px; font-weight: 700; color: #0f172a; }
    .mth-cell-note { font-size: 12px; color: #64748b; line-height: 1.55; }

    .mth-hfte { display: flex; align-items: stretch; gap: 14px; flex-wrap: wrap; }
    .mth-hfte-side { flex: 1; min-width: 240px; border-radius: 10px; padding: 16px 18px; }
    .mth-hfte-side.pos { background: #f0fdf4; border: 1px solid #dcfce7; }
    .mth-hfte-side.neg { background: #fef2f2; border: 1px solid #fee2e2; }
    .mth-hfte-title { font-size: 11px; font-weight: 800; text-transform: uppercase;
                      letter-spacing: 0.4px; margin-bottom: 10px; }
    .mth-hfte-side.pos .mth-hfte-title { color: #15803d; }
    .mth-hfte-side.neg .mth-hfte-title { color: #b91c1c; }

    .mth-na { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
              background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;
              padding: 12px 16px; margin-bottom: 18px; }
    .mth-na-label { font-size: 11px; font-weight: 800; color: #64748b;
                    text-transform: uppercase; letter-spacing: 0.4px; }
    .mth-na-chip { font-size: 11.5px; font-weight: 600; color: #475569;
                   background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 3px 11px; }

    .mth-coach { background: #eff6ff; border: 1px solid #dbeafe; border-radius: 10px;
                 padding: 20px 24px; margin-top: 6px; }
    .mth-coach-row { display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; }
    .mth-coach-row:last-child { margin-bottom: 0; }
    .mth-coach-key { font-size: 11px; font-weight: 800; color: #1e40af; text-transform: uppercase;
                     letter-spacing: 0.4px; min-width: 128px; padding-top: 2px; }
    .mth-coach-val { font-size: 13px; color: #1e3a8a; line-height: 1.65; flex: 1; }

    /* ---- Verbose scorecard table ---- */
    .mth-sc { width: 100%; border-collapse: collapse; font-size: 13px; }
    .mth-sc thead th {
      text-align: left; font-size: 10.5px; font-weight: 800; color: #94a3b8;
      text-transform: uppercase; letter-spacing: .5px;
      padding: 0 14px 10px; border-bottom: 1px solid #e2e8f0;
    }
    .mth-sc tbody td { padding: 15px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
    .mth-sc tbody tr:last-child td { border-bottom: none; }
    .mth-sc-name { font-weight: 700; color: #0f172a; white-space: nowrap; }
    .mth-sc-ch { display: block; font-size: 11px; color: #94a3b8; font-weight: 600; margin-top: 3px; }
    .mth-sc-pts { font-weight: 800; color: #0f172a; white-space: nowrap; text-align: right; }
    .mth-sc-pct { font-weight: 800; white-space: nowrap; text-align: right; }
    .mth-sc-wt2 { font-weight: 600; color: #94a3b8; white-space: nowrap; text-align: right; }
    .mth-ft td { padding: 11px 14px; border: none; }
    .mth-ft-top td { border-top: 2px solid #e2e8f0; padding-top: 15px; }
    .mth-ft-lbl { text-align: right; font-size: 12.5px; color: #475569; font-weight: 600; }
    .mth-ft-sub { display: block; font-size: 10.5px; color: #94a3b8; font-weight: 500; margin-top: 2px; }
    .mth-ft-den { font-size: 11px; font-weight: 700; color: #94a3b8; }
    .mth-ft-grand td { background: #0f172a; padding: 15px 14px; }
    .mth-ft-grand .mth-ft-lbl { color: #94a3b8; font-size: 11px; font-weight: 800;
                                text-transform: uppercase; letter-spacing: .5px; }
    .mth-ft-grand .mth-sc-pts { color: #fff; font-size: 20px; }
    .mth-ft-grand .mth-ft-den { color: #64748b; font-size: 12px; }
    .mth-ft-grand td:first-child { border-radius: 8px 0 0 8px; }
    .mth-ft-grand td:last-child { border-radius: 0 8px 8px 0; }
    .mth-ft-grade { font-size: 12px; font-weight: 800; white-space: nowrap; }
    .mth-sc-wt { display: block; font-size: 10.5px; font-weight: 700; color: #94a3b8;
                 margin-top: 3px; letter-spacing: .2px; }
    .mth-sc-obs { color: #475569; line-height: 1.65; }
    .mth-sc-na td { background: #f8fafc; color: #94a3b8; }
    .mth-sc-count { font-size: 11px; font-weight: 700; color: #64748b;
                    background: #f1f5f9; padding: 3px 11px; border-radius: 11px; }

    .mth-warn { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
                padding: 12px 16px; margin-bottom: 18px; font-size: 12.5px; color: #92400e; line-height: 1.6; }

    @media (max-width: 720px) {
      .mth-rail { flex-direction: column; gap: 14px; }
      .mth-stage { text-align: left; display: flex; gap: 12px; align-items: flex-start; }
      .mth-stage::before { display: none; }
      .mth-stage-dot { margin: 0; flex-shrink: 0; }
      .mth-scorebar-wrap { flex-wrap: wrap; }
      .mth-scorebar-label { min-width: 100%; }
    }
    """


# =============================================================================
# Fragments
# =============================================================================

def _band_chip(band: str) -> str:
    color, bg, label = BAND_STYLE.get(band, BAND_STYLE["missing"])
    return f'<span class="mth-band" style="background:{bg};color:{color}">{e(label)}</span>'


def _status_chip(status: str) -> str:
    color, bg, label = STATUS_STYLE.get(status, STATUS_STYLE["not_applicable"])
    return f'<span class="mth-band" style="background:{bg};color:{color}">{e(label)}</span>'


def _score_bar(label: str, score: float, maximum: float, color: str) -> str:
    pct = round(100 * score / maximum) if maximum else 0
    return f"""
      <div class="mth-scorebar-wrap">
        <span class="mth-scorebar-label">{e(label)}</span>
        <div class="mth-scorebar-bg"><div class="mth-scorebar-fill"
             style="width:{pct}%;background:{color}"></div></div>
        <span class="mth-scorebar-pts">{score:.0f} / {maximum:.0f}</span>
      </div>"""


def _trust_rail(tj: dict) -> str:
    reached = {s["id"] for s in tj.get("stages", []) if s.get("reached")}
    furthest = tj.get("furthest_stage_reached")
    notes = {s["id"]: s for s in tj.get("stages", [])}

    cells = []
    for idx, (sid, name, feeling) in enumerate(TRUST_STAGES, start=1):
        is_reached = sid in reached
        is_stall = sid == furthest
        cls = "mth-stage" + (" reached" if is_reached else "") + (" stall" if is_stall else "")
        mark = "&#10003;" if is_reached and not is_stall else str(idx)
        note = notes.get(sid, {}).get("note") or feeling
        cells.append(f"""
        <div class="{cls}">
          <div class="mth-stage-dot">{mark}</div>
          <div>
            <div class="mth-stage-name">{e(name)}</div>
            <div class="mth-stage-feel">{e(note)}</div>
          </div>
        </div>""")

    stall = tj.get("where_it_stalled")
    stall_html = ""
    if stall:
        label = next((n for i, n, _ in TRUST_STAGES if i == furthest), furthest or "the start")
        stall_html = (f'<div class="mth-stall-note">Conversation stalled at '
                      f'<b>{e(label)}</b> &mdash; {e(stall)}</div>')
    else:
        stall_html = ('<div class="mth-stall-note">Reached <b>I\'ll Decide</b> '
                      '&mdash; the full trust journey was completed.</div>')

    return f"""
    <div class="mth-trust">
      <div class="mth-trust-title">Trust Journey &mdash; how far confidence actually travelled</div>
      <div class="mth-rail">{''.join(cells)}</div>
      {stall_html}
    </div>"""


def _trust_rail_section(tj: dict) -> str:
    return f'''
  <div class="section">
    <div class="section-title">Trust Journey</div>
    {_trust_rail(tj)}
  </div>'''


def _dimension(d: dict, chapters: dict[str, str]) -> str:
    color = BAND_STYLE.get(d["band"], BAND_STYLE["missing"])[0]

    quotes = "".join(
        f'<div class="mth-quote"><span class="mth-quote-ts">{e(q.get("timestamp"))}</span>'
        f'{e(q.get("quote"))}</div>'
        for q in d.get("evidence", [])
    )

    misses = ""
    for m in d.get("missed_opportunities", []) or []:
        better = (f'<div class="mth-miss-better"><b>Try:</b> &ldquo;{e(m["better_response"])}&rdquo;</div>'
                  if m.get("better_response") else "")
        misses += f"""
        <div class="mth-miss">
          <div class="mth-miss-head">Missed opportunity &middot; {e(m.get('timestamp'))}</div>
          <div class="mth-miss-row"><b>What happened:</b> {e(m.get('what_happened'))}</div>
          <div class="mth-miss-row"><b>The Bible says:</b> {e(m.get('bible_says'))}</div>
          {better}
        </div>"""

    return f"""
    <div class="mth-dim">
      <div class="mth-dim-head">
        <span class="mth-dim-name">{e(d['name'])}</span>
        {_band_chip(d['band'])}
        <span class="mth-dim-chapter">{e(chapters.get(d['id'], ''))}</span>
        <span class="mth-dim-pts">{d['pct']:.0f}%
          <span style="color:#94a3b8;font-weight:600">&middot; weight {d.get('weight', 0):.0f}%
          &middot; {d['points']:.1f} pts</span></span>
      </div>
      <div class="mth-scorebar-bg" style="margin-bottom:10px">
        <div class="mth-scorebar-fill" style="width:{d['pct']:.0f}%;background:{color}"></div>
      </div>
      <div class="mth-dim-reason">{e(d.get('reasoning'))}</div>
      {quotes}
      {misses}
    </div>"""


def _apportion(values: list[float], decimals: int = 1) -> list[float]:
    """Round a list so the displayed values sum to the displayed total.

    Naive per-row rounding breaks the column: 2.52 and 3.15 print as 2.5 and
    3.1, which read as 5.6, while the true subtotal 5.67 prints as 5.7. A
    manager checking the arithmetic finds it off by 0.1 and stops trusting the
    table. Largest-remainder apportionment (the standard fix in financial
    reporting) pushes the rounding into whichever rows are closest to rounding
    up, so the column always adds up to what the footer says.
    """
    if not values:
        return []
    step = 10 ** decimals
    target = round(round(sum(values), decimals) * step)
    floors = [int(v * step) for v in values]
    shortfall = target - sum(floors)
    # rank by how close each value was to rounding up
    order = sorted(range(len(values)), key=lambda i: (values[i] * step) - floors[i], reverse=True)
    for i in order[:max(0, shortfall)]:
        floors[i] += 1
    return [f / step for f in floors]


def _weight_cell(d: dict) -> str:
    """Show the weight the points were actually computed from.

    With every stage applicable the raw rubric weight is the effective one.
    When a stage is N/A the rest are renormalised upward, so showing the raw
    weight makes the row's own arithmetic look wrong.
    """
    if not d.get("renormalized"):
        return f"{d.get('weight', 0):.0f}%"
    return (f"{d.get('effective_weight', 0):.1f}%"
            f"<span class=\"mth-sc-wt\">of {d.get('weight', 0):.0f}% base</span>")


def _scorecard(score: dict, chapters: dict[str, str]) -> str:
    """Dense criteria table with the full arithmetic shown in the footer.

    Percentages, not "x / 10" — seven rows each out of 10 reads as a score out
    of 70, which is the wrong mental model. A percentage carries no implied
    denominator, so the rows cannot be misread as adding up to anything.

    The POINTS column is what actually sums, and the footer runs the whole
    calculation to the final score, so a manager can see where the number came
    from without being walked through it.
    """
    meth = score.get("_methodology", {})
    dims = meth.get("dimensions", [])
    shown = _apportion([d["points"] for d in dims])
    rows = ""
    for d, pts in zip(dims, shown):
        color = BAND_STYLE.get(d["band"], BAND_STYLE["missing"])[0]
        rows += f"""
        <tr>
          <td class="mth-sc-name">{e(d['name'])}
            <span class="mth-sc-ch">{e(chapters.get(d['id'], ''))}</span></td>
          <td style="width:1%">{_band_chip(d['band'])}</td>
          <td class="mth-sc-pct" style="width:1%;color:{color}">{d['pct']:.0f}%</td>
          <td class="mth-sc-wt2" style="width:1%">{_weight_cell(d)}</td>
          <td class="mth-sc-pts" style="width:1%">{pts:.1f}</td>
          <td class="mth-sc-obs">{e(d.get('reasoning'))}</td>
        </tr>"""

    for na in meth.get("not_applicable", []):
        na_weight = na.get("weight", 0)
        rows += f"""
        <tr class="mth-sc-na">
          <td class="mth-sc-name" style="color:#94a3b8">{e(na['name'])}
            <span class="mth-sc-ch">{e(chapters.get(na['id'], ''))}</span></td>
          <td style="width:1%">{_status_chip('not_applicable')}</td>
          <td class="mth-sc-pct" style="color:#cbd5e1">&mdash;</td>
          <td class="mth-sc-wt2" style="color:#cbd5e1">&mdash;</td>
          <td class="mth-sc-pts" style="color:#cbd5e1">&mdash;</td>
          <td class="mth-sc-obs" style="color:#94a3b8">
            Stage not reached on this call &mdash; excluded from scoring. Its
            {na_weight:.0f}% weight is redistributed across the criteria above,
            which is why their effective weights exceed their base weights.</td>
        </tr>"""

    pens = meth.get("penalties", {})
    pen_total = pens.get("total", 0) or 0
    subtotal = round(sum(shown), 1)
    meth_score = meth.get("score", 0)
    meth_max = meth.get("max", 60)
    achievable = meth.get("achievable", meth_max)
    # When renormalisation is off and a stage was N/A, the ceiling is below the
    # full 60. Showing "/ 60" would understate the rep against a target they
    # could not have reached.
    meth_den = (f"{achievable:.1f} achievable of {meth_max:.0f}"
                if abs(achievable - meth_max) > 0.05 else f"{meth_max:.0f}")
    comp_score = score.get("compliance_score", 0)
    comp_max = score.get("compliance_max", 40)
    total = score.get("total_score", 0)

    pen_row = ""
    if pen_total:
        pen_row = f"""
          <tr class="mth-ft">
            <td colspan="4" class="mth-ft-lbl">Habit penalties
              <span class="mth-ft-sub">capped at 30% of points earned</span></td>
            <td class="mth-sc-pts" style="color:#dc2626">&minus;{pen_total:.1f}</td><td></td>
          </tr>"""

    cap_row = ""
    if score.get("cap_applied"):
        cap_row = f"""
          <tr class="mth-ft">
            <td colspan="4" class="mth-ft-lbl" style="color:#b45309">Compliance cap applied
              <span class="mth-ft-sub">{e(score.get('cap_reason'))}</span></td>
            <td class="mth-sc-pts" style="color:#b45309">{score['cap_applied']}</td><td></td>
          </tr>"""

    n = len(meth.get("dimensions", []))
    return f"""
    <div class="section">
      <div class="section-title" style="display:flex;align-items:center;
           justify-content:space-between;gap:12px">
        <span>Detailed Rubric Scorecard</span>
        <span class="mth-sc-count">{n} criteria evaluated</span>
      </div>
      <div class="card" style="padding:22px 14px">
        <table class="mth-sc">
          <thead><tr>
            <th>Evaluation Criteria</th>
            <th>Band</th>
            <th style="text-align:right">Achieved</th>
            <th style="text-align:right">Weight</th>
            <th style="text-align:right">Points</th>
            <th>Key Assessment &amp; Observations</th>
          </tr></thead>
          <tbody>{rows}</tbody>
          <tfoot>
            <tr class="mth-ft mth-ft-top">
              <td colspan="4" class="mth-ft-lbl">Sales Bible subtotal</td>
              <td class="mth-sc-pts">{subtotal:.1f}</td><td></td>
            </tr>
            {pen_row}
            <tr class="mth-ft">
              <td colspan="4" class="mth-ft-lbl"><b>Methodology</b></td>
              <td class="mth-sc-pts"><b>{meth_score:.1f}</b>
                <span class="mth-ft-den"> / {meth_den}</span></td><td></td>
            </tr>
            <tr class="mth-ft">
              <td colspan="4" class="mth-ft-lbl"><b>Compliance</b>
                <span class="mth-ft-sub">from the Incident Report tab</span></td>
              <td class="mth-sc-pts"><b>{comp_score:.1f}</b>
                <span class="mth-ft-den"> / {comp_max:.0f}</span></td><td></td>
            </tr>
            {cap_row}
            <tr class="mth-ft mth-ft-grand">
              <td colspan="4" class="mth-ft-lbl">TOTAL CALL SCORE</td>
              <td class="mth-sc-pts">{total}<span class="mth-ft-den"> / 100</span></td>
              <td class="mth-ft-grade" style="color:{e(score.get('grade_color'))}">
                {e(score.get('grade'))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>"""


def _four_whys(items: list[dict]) -> str:
    if not items:
        return ""
    cells = "".join(f"""
      <div class="mth-cell">
        <div class="mth-cell-head">
          <span class="mth-cell-label">{e(WHY_LABELS.get(w.get('id'), w.get('id')))}</span>
          {_status_chip(w.get('status', 'unanswered'))}
        </div>
        <div class="mth-cell-note">{e(w.get('note'))}</div>
      </div>""" for w in items)
    return f"""
    <div class="section">
      <div class="section-title">The 4 WHYs &mdash; questions the customer needed answered</div>
      <div class="card"><div class="mth-grid">{cells}</div></div>
    </div>"""


def _hfte(items: list[dict]) -> str:
    if not items:
        return ""
    by_id = {i.get("id"): i for i in items}

    def side(ids: list[str], cls: str, title: str) -> str:
        rows = ""
        for i in ids:
            it = by_id.get(i, {})
            rows += f"""
            <div class="mth-cell" style="margin-bottom:8px">
              <div class="mth-cell-head">
                <span class="mth-cell-label">{e(HFTE_LABELS.get(i, i))}</span>
                {_status_chip(it.get('status', 'not_addressed'))}
              </div>
              <div class="mth-cell-note">{e(it.get('note'))}</div>
            </div>"""
        return f'<div class="mth-hfte-side {cls}"><div class="mth-hfte-title">{e(title)}</div>{rows}</div>'

    return f"""
    <div class="section">
      <div class="section-title">HFTE Balance &mdash; Hope + Trust must outweigh Fear + Effort</div>
      <div class="card">
        <div class="mth-hfte">
          {side(['hope', 'trust'], 'pos', 'Drivers toward a decision')}
          {side(['fear', 'effort'], 'neg', 'Drivers against a decision')}
        </div>
      </div>
    </div>"""


# =============================================================================
# Main renderer
# =============================================================================

def render_methodology_section(score: dict, chapters: dict[str, str] | None = None) -> str:
    """Render the full section from the output of scoring.compute_overall_score."""
    meth = score.get("_methodology", {})
    comp = score.get("_compliance", {})
    chapters = chapters or {}

    # --- Score summary -------------------------------------------------------
    # Titled "Sales Bible Rubric Score", NOT "Overall Call Score" — the latter
    # is the pre-existing sales-pitch section and the two are independent
    # measurements. Sharing a title would invite them to be read as one number.
    bars = _score_bar("Compliance & Fact Accuracy",
                      score["compliance_score"], score["compliance_max"], "#2563eb")
    bars += _score_bar("Sales Bible Methodology",
                       score["methodology_score"], score["methodology_max"], "#8b5cf6")

    warnings = ""
    if score.get("cap_reason"):
        warnings += (f'<div class="mth-warn"><b>Score capped.</b> {e(score["cap_reason"])}. '
                     f'Methodology strength does not offset a compliance breach.</div>')
    if score.get("low_confidence"):
        warnings += ('<div class="mth-warn"><b>Low confidence.</b> This call was short, '
                     'one-sided, or reached too few stages for a reliable methodology read. '
                     'Treat the score as indicative and review manually.</div>')

    na = ""
    if meth.get("not_applicable"):
        chips = "".join(f'<span class="mth-na-chip">{e(x["name"])}</span>'
                        for x in meth["not_applicable"])
        na = (f'<div class="mth-na"><span class="mth-na-label">Stages not reached '
              f'&mdash; excluded from scoring</span>{chips}</div>')

    # --- Penalties -----------------------------------------------------------
    pens = meth.get("penalties", {})
    pen = pens.get("applied", [])
    pen_html = ""
    if pen:
        rows = "".join(f'<div class="mth-miss-row">&minus;{p["points"]} &nbsp; {e(p["reason"])}</div>'
                       for p in pen)
        applied_total = pens.get("total", 0)
        raw_total = pens.get("total_uncapped", applied_total)
        # When the proportional cap bites, say so — otherwise a header reading
        # "-1.2 total" above a list summing to -14 looks like an arithmetic bug.
        if pens.get("proportionally_capped"):
            head = (f"Behavioural penalties &mdash; &minus;{applied_total:.1f} applied "
                    f"(of &minus;{raw_total:.0f} identified)")
            note = ('<div class="mth-miss-row" style="margin-top:8px;font-size:11.5px;color:#94a3b8">'
                    'Penalties are capped at a share of the points earned, so behaviour already '
                    'reflected in the band ratings above is not deducted twice.</div>')
        else:
            head = f"Behavioural penalties &mdash; &minus;{applied_total:.1f} total"
            note = ""
        pen_html = f"""
        <div class="mth-miss" style="border-left-color:#ef4444;background:#fef2f2">
          <div class="mth-miss-head" style="color:#b91c1c">{head}</div>{rows}{note}
        </div>"""

    dims = "".join(_dimension(d, chapters) for d in meth.get("dimensions", []))

    coach = score.get("coaching_summary") or meth.get("coaching_summary") or {}
    coach_html = ""
    if coach:
        rows = ""
        for key, label in (("top_strength", "Top strength"),
                           ("top_priority", "Highest-leverage fix"),
                           ("one_behaviour_to_practice", "Next 10 calls")):
            if coach.get(key):
                rows += (f'<div class="mth-coach-row"><span class="mth-coach-key">{e(label)}</span>'
                         f'<span class="mth-coach-val">{e(coach[key])}</span></div>')
        coach_html = f"""
        <div class="section">
          <div class="section-title">Coaching Focus</div>
          <div class="mth-coach">{rows}</div>
        </div>"""

    return f"""
  <div class="section">
    <div class="section-title">Sales Bible Rubric Score</div>
    <div class="card">
      {warnings}
      <div style="display:flex;align-items:center;gap:32px;flex-wrap:wrap;margin-bottom:22px">
        <div style="text-align:center;min-width:150px">
          <div style="font-size:52px;font-weight:800;color:{e(score['grade_color'])};
                      line-height:1;letter-spacing:-2px">{score['total_score']}</div>
          <div style="font-size:12px;color:#94a3b8;font-weight:700;margin-top:4px">out of 100</div>
          <div style="font-size:13px;font-weight:800;color:{e(score['grade_color'])};
                      margin-top:8px">{e(score['grade'])}</div>
        </div>
        <div style="flex-grow:1;min-width:300px">{bars}</div>
      </div>
      <div style="font-size:12.5px;color:#64748b;line-height:1.65;border-top:1px solid #f1f5f9;
                  padding-top:14px">{e(score.get('deductions_text'))}</div>
      <div style="font-size:11px;color:#cbd5e1;margin-top:10px">
        Rubric v{e(score.get('rubric_version'))} &middot; Scoring v{e(score.get('scoring_version'))}
        &middot; Independent of the Sales Pitch score
      </div>
    </div>
  </div>

  {_trust_rail_section(meth.get('trust_journey', {}))}

  {_scorecard(score, chapters)}

  <div class="section">
    <div class="section-title">Evidence &amp; Coaching Detail</div>
    {na}
    {pen_html}
    {dims}
  </div>

  {_four_whys(meth.get('four_whys', []))}
  {_hfte(meth.get('hfte_balance', []))}
  {coach_html}
"""