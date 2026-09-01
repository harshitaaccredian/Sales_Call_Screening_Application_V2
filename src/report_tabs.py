"""
Tab shell for the call quality report.

Wraps the existing report body (Incident Report) and the new Sales Bible
assessment (Rubric Report) into two switchable tabs, without touching either
one's markup.

Design notes
------------
- No framework. The existing report is vanilla CSS on a slate palette; pulling
  in a Tailwind CDN for two tabs would add a network dependency to a file that
  is often opened straight from disk or emailed as an attachment.
- Tabs work without JavaScript. The CSS `:checked` sibling selector drives
  visibility off hidden radio inputs, so the report degrades to a working
  document in any renderer that blocks scripts (many email clients, some PDF
  converters). The small script only adds deep-linking via #hash.
- Print stylesheet expands every panel, so Cmd-P still produces the full report
  rather than whichever tab happened to be open.

Usage
-----
    from src.report_tabs import tabs_css, render_tabs

    body = render_tabs([
        ("incident", "Incident Report", incident_html),
        ("rubric",   "Rubric Report",   rubric_html),
    ])
"""

from __future__ import annotations

import html as _html


def tabs_css() -> str:
    return """
    /* ---- Report tabs ---- */
    .rt-tabs { margin-bottom: 28px; }
    .rt-radio { position: absolute; opacity: 0; pointer-events: none; }

    .rt-tablist {
      display: flex; gap: 4px; flex-wrap: wrap;
      background: #f1f5f9; border-radius: 10px; padding: 5px;
      margin-bottom: 26px;
    }
    .rt-tab {
      flex: 1; min-width: 150px; text-align: center; cursor: pointer;
      padding: 11px 20px; border-radius: 7px;
      font-size: 13px; font-weight: 700; color: #64748b;
      transition: background .15s ease, color .15s ease;
      user-select: none; display: flex; align-items: center;
      justify-content: center; gap: 9px;
    }
    .rt-tab:hover { color: #0f172a; background: rgba(255,255,255,.55); }
    .rt-tab:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }

    .rt-badge {
      font-size: 11px; font-weight: 800; padding: 2px 9px; border-radius: 11px;
      background: #e2e8f0; color: #475569; line-height: 1.5;
    }

    .rt-panel { display: none; }

    /* Radio N checked -> highlight label N, show panel N. */
    #rt-0:checked ~ .rt-tablist label[for="rt-0"],
    #rt-1:checked ~ .rt-tablist label[for="rt-1"],
    #rt-2:checked ~ .rt-tablist label[for="rt-2"] {
      background: #fff; color: #0f172a;
      box-shadow: 0 1px 3px rgba(15,23,42,.10);
    }
    #rt-0:checked ~ .rt-tablist label[for="rt-0"] .rt-badge,
    #rt-1:checked ~ .rt-tablist label[for="rt-1"] .rt-badge,
    #rt-2:checked ~ .rt-tablist label[for="rt-2"] .rt-badge {
      background: #dbeafe; color: #1e40af;
    }
    #rt-0:checked ~ .rt-panels > #rt-panel-0,
    #rt-1:checked ~ .rt-panels > #rt-panel-1,
    #rt-2:checked ~ .rt-panels > #rt-panel-2 { display: block; }

    /* No-JS / unsupported-selector fallback: if nothing is checked the first
       panel still shows, so the report is never blank. */
    .rt-panels > .rt-panel:first-child { display: block; }
    #rt-1:checked ~ .rt-panels > .rt-panel:first-child,
    #rt-2:checked ~ .rt-panels > .rt-panel:first-child { display: none; }

    @media print {
      .rt-tablist { display: none; }
      .rt-panel, .rt-panels > .rt-panel:first-child { display: block !important; }
      .rt-panel + .rt-panel { page-break-before: always; }
    }
    @media (max-width: 640px) {
      .rt-tab { min-width: 100%; }
    }
    """


def render_tabs(panels: list[tuple[str, str, str]], badges: dict[str, str] | None = None) -> str:
    """Build the tab shell.

    Args:
        panels: list of (slug, label, inner_html), in display order.
        badges: optional {slug: badge_text}, e.g. {"incident": "3", "rubric": "62"}.

    Returns the complete tabs markup. Requires tabs_css() in the stylesheet.
    """
    badges = badges or {}
    e = lambda v: _html.escape(str(v), quote=True)

    radios = "".join(
        f'<input class="rt-radio" type="radio" name="rt" id="rt-{i}"'
        f'{" checked" if i == 0 else ""}>'
        for i in range(len(panels))
    )

    tabs = ""
    for i, (slug, label, _) in enumerate(panels):
        badge = (f'<span class="rt-badge">{e(badges[slug])}</span>'
                 if slug in badges and badges[slug] not in (None, "") else "")
        tabs += (f'<label class="rt-tab" for="rt-{i}" tabindex="0" '
                 f'role="tab" data-slug="{e(slug)}">{e(label)}{badge}</label>')

    body = "".join(
        f'<div class="rt-panel" id="rt-panel-{i}" data-slug="{e(slug)}" role="tabpanel">{inner}</div>'
        for i, (slug, _, inner) in enumerate(panels)
    )

    # Progressive enhancement only: keyboard activation and #hash deep-linking.
    script = """
<script>
(function () {
  var labels = document.querySelectorAll('.rt-tab');
  function select(slug) {
    for (var i = 0; i < labels.length; i++) {
      if (labels[i].dataset.slug === slug) {
        var r = document.getElementById(labels[i].getAttribute('for'));
        if (r) { r.checked = true; }
        return true;
      }
    }
    return false;
  }
  labels.forEach(function (el) {
    el.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); el.click(); }
    });
    el.addEventListener('click', function () {
      if (history.replaceState) {
        history.replaceState(null, '', '#' + el.dataset.slug);
      }
    });
  });
  if (location.hash) { select(location.hash.slice(1)); }
})();
</script>"""

    return (f'<div class="rt-tabs">{radios}'
            f'<div class="rt-tablist" role="tablist">{tabs}</div>'
            f'<div class="rt-panels">{body}</div></div>{script}')