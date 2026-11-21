"""
views/dashboard_ui.py
=====================
HTML and CSS for the dashboard's card-style layout (KPI cards, legend, status list, progress ring).

Every function returns a string and escapes all text it receives (column names and category values come
from the user's file), so nothing here can inject markup. All colours are defined once below and the CSS is
generated from them; ``tests/test_dashboard_ui.py`` checks the text/background pairs meet WCAG AA contrast.
"""
from __future__ import annotations

import html

from views.common import CHART_COLORS, TOKENS

# ----- palette (single source of truth: the shared design tokens in views/common.py) ----------
NAVY = TOKENS["sidebar-bg"]                 # sidebar
NAVY_HOVER = TOKENS["sidebar-hover"]        # sidebar item hover
NAVY_ACTIVE = TOKENS["sidebar-active"]      # active sidebar item background (indigo)
NAVY_ACTIVE_BORDER = TOKENS["sidebar-active"]
ON_NAVY = TOKENS["sidebar-text-strong"]
PAGE_BG = TOKENS["surface"]
CARD_BG = TOKENS["card"]
CARD_BORDER = TOKENS["border"]
TITLE = TOKENS["text"]
MUTED = TOKENS["text-secondary"]
TONES = {  # tone -> (text colour, pill background)
    "good": (TOKENS["teal-text"], TOKENS["teal-light"]),
    "bad": (TOKENS["rose-text"], TOKENS["rose-light"]),
    "warn": (TOKENS["amber-text"], TOKENS["amber-light"]),
    "neutral": (TOKENS["text-secondary"], TOKENS["indigo-light"]),
}
ICON_COLORS = {"records": TOKENS["indigo"], "metric": TOKENS["teal"], "completeness": "#364776", "segments": "#6366f1"}
ICON_TINTS = {"records": TOKENS["indigo-light"], "metric": TOKENS["teal-light"], "completeness": "#eef2fb", "segments": "#eef2ff"}
DONUT_PALETTE = CHART_COLORS[:6]
RING_COLOR = TOKENS["teal"]
RING_TRACK = TOKENS["border"]

#: (description, text colour, background colour): each must reach 4.5:1 (checked by tests).
TEXT_PAIRS: list[tuple[str, str, str]] = [
    ("title on card", TITLE, CARD_BG), ("muted on card", MUTED, CARD_BG), ("title on page", TITLE, PAGE_BG),
    ("muted on page", MUTED, PAGE_BG), ("sidebar text", ON_NAVY, NAVY), ("sidebar hover", ON_NAVY, NAVY_HOVER),
    ("sidebar active", ON_NAVY, NAVY_ACTIVE),
    *[(f"{tone} pill", fg, bg) for tone, (fg, bg) in TONES.items()],
    *[(f"{tone} text on card", fg, CARD_BG) for tone, (fg, _bg) in TONES.items()],
]

_ICON_PATHS = {
    "records": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
               '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "metric": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>'
              '<line x1="6" y1="20" x2="6" y2="14"/>',
    "completeness": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "segments": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/>'
                '<polyline points="2 12 12 17 22 12"/>',
    "check": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
}
_ARROWS = {"up": "▲", "down": "▼", "flat": "•"}
_STATUS_LABELS = {"ok": ("Good", "good", "✓"), "warn": ("Review", "warn", "!"), "bad": ("Fix", "bad", "✕")}


def esc(value: object) -> str:
    """HTML-escape any value (including quotes) for safe insertion into markup."""
    return html.escape(str(value), quote=True)


def _icon(name: str, stroke: str = "#ffffff", size: int = 22) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICON_PATHS[name]}</svg>')


def kpi_card_html(card: dict) -> str:
    """One KPI card from ``data.dashboard_cards.kpi_cards``: label and icon, value, caption, change-vs-full-dataset pill."""
    key = card["key"]
    tone = card.get("tone", "neutral")
    arrow = _ARROWS.get(card.get("direction", "flat"), "•")
    delta = (f'<div class="dash-kpi-delta dash-tone-{esc(tone)}"><span>{arrow} {esc(card["delta_text"])}</span>'
             f'<small>{esc(card["delta_note"])}</small></div>')
    colour = ICON_COLORS.get(key, TOKENS["indigo"])
    tint = ICON_TINTS.get(key, TOKENS["indigo-light"])
    return (
        f'<div class="dash-kpi" role="group" aria-label="{esc(card["label"])}">'
        f'<div class="dash-kpi-top"><div class="dash-kpi-label">{esc(card["label"])}</div>'
        f'<div class="dash-kpi-icon" style="background:{tint}">{_icon(key, colour, 20)}</div></div>'
        f'<div class="dash-kpi-value">{esc(card["value"])}</div>'
        f'<div class="dash-kpi-caption">{esc(card["caption"])}</div>{delta}</div>'
    )


def kpi_row_html(cards: list[dict]) -> str:
    """The responsive grid of KPI cards."""
    return '<div class="dash-kpi-grid">' + "".join(kpi_card_html(c) for c in cards) + "</div>"


def card_title_html(title: str, hint: str = "") -> str:
    hint_html = f'<span class="dash-card-hint">{esc(hint)}</span>' if hint else ""
    return f'<div class="dash-card-title">{esc(title)}{hint_html}</div>'


def legend_html(items: list[dict], value_text) -> str:
    """Coloured legend rows (label, value, share) matching a donut drawn with ``DONUT_PALETTE``."""
    rows = []
    for i, item in enumerate(items):
        color = DONUT_PALETTE[i % len(DONUT_PALETTE)]
        rows.append(
            f'<div class="dash-legend-row"><span class="dash-dot" style="background:{color}"></span>'
            f'<span class="dash-legend-label">{esc(item["label"])}</span>'
            f'<span class="dash-legend-value">{esc(value_text(item["value"]))}</span>'
            f'<span class="dash-legend-share">{item["share"] * 100:.1f}%</span></div>'
        )
    return '<div class="dash-legend">' + "".join(rows) + "</div>"


def status_list_html(checks: list[dict]) -> str:
    """Rows of ``{name, detail, status}`` with a coloured status pill (never colour alone: it has a word and a symbol)."""
    rows = []
    for check in checks:
        label, tone, symbol = _STATUS_LABELS.get(check["status"], _STATUS_LABELS["warn"])
        rows.append(
            f'<div class="dash-status-row"><div class="dash-status-icon">{_icon("check", TOKENS["indigo"], 18)}</div>'
            f'<div class="dash-status-text"><div class="dash-status-name">{esc(check["name"])}</div>'
            f'<div class="dash-status-detail">{esc(check["detail"])}</div></div>'
            f'<span class="dash-pill dash-tone-{tone}">{symbol} {label}</span></div>'
        )
    return '<div class="dash-status">' + "".join(rows) + "</div>"


def ring_html(percent: float, centre_value: str, centre_label: str, stats: list[tuple[str, str]]) -> str:
    """A circular progress ring with a centre label and a row of small stats underneath."""
    percent = max(0.0, min(100.0, float(percent)))
    circumference = 2 * 3.14159265 * 52
    filled = circumference * percent / 100
    stat_html = "".join(f'<div><div class="dash-ring-stat-value">{esc(v)}</div>'
                        f'<div class="dash-ring-stat-label">{esc(label)}</div></div>' for v, label in stats)
    return (
        f'<div class="dash-ring" role="img" aria-label="{esc(centre_label)}: {percent:.0f}%">'
        f'<svg viewBox="0 0 120 120" width="170" height="170"><circle cx="60" cy="60" r="52" fill="none" '
        f'stroke="{RING_TRACK}" stroke-width="12"/><circle cx="60" cy="60" r="52" fill="none" stroke="{RING_COLOR}" '
        f'stroke-width="12" stroke-linecap="round" stroke-dasharray="{filled:.2f} {circumference:.2f}" '
        f'transform="rotate(-90 60 60)"/>'
        f'<text x="60" y="58" text-anchor="middle" class="dash-ring-value">{esc(centre_value)}</text>'
        f'<text x="60" y="76" text-anchor="middle" class="dash-ring-caption">{esc(centre_label)}</text></svg>'
        f'<div class="dash-ring-stats">{stat_html}</div></div>'
    )


def header_html(title: str, subtitle: str) -> str:
    return (f'<div class="dash-header"><div><div class="dash-title">{esc(title)}</div>'
            f'<div class="dash-subtitle">{esc(subtitle)}</div></div></div>')


_CSS_TEMPLATE = """
<style>
[data-testid="stAppViewContainer"] { background: %PAGE_BG%; }
.dash-header { display:flex; align-items:center; justify-content:space-between; margin:2px 0 10px; }
.dash-title { font-size:20px; font-weight:600; color:%TITLE%; line-height:1.3; }
.dash-subtitle { font-size:14px; color:%MUTED%; }

/* KPI cards: label + icon, large tabular value, caption, change pill */
.dash-kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(235px,1fr)); gap:16px; margin:8px 0 16px; }
.dash-kpi { display:flex; flex-direction:column; gap:4px; background:%CARD_BG%; border:1px solid %CARD_BORDER%;
  border-radius:var(--ap-radius-card,12px); padding:16px 18px; box-shadow:var(--ap-shadow); min-width:0; }
.dash-kpi-top { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.dash-kpi-label { font-size:13px; font-weight:500; color:%MUTED%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.dash-kpi-icon { width:36px; height:36px; flex:0 0 36px; border-radius:var(--ap-radius-control,8px); display:flex; align-items:center; justify-content:center; }
.dash-kpi-value { font-size:clamp(1.6rem,2.3vw,2rem); font-weight:700; color:%TITLE%; line-height:1.15; letter-spacing:-.02em;
  font-variant-numeric:tabular-nums; overflow-wrap:anywhere; margin-top:2px; }
.dash-kpi-caption { font-size:12px; color:%MUTED%; line-height:1.4; }
.dash-kpi-delta { display:flex; align-items:center; flex-wrap:wrap; gap:4px 8px; margin-top:8px; font-size:12px; font-weight:600; }
.dash-kpi-delta span { padding:2px 8px; border-radius:var(--ap-radius-pill,9999px); white-space:nowrap; font-variant-numeric:tabular-nums; }
.dash-kpi-delta small { font-weight:400; color:%MUTED%; font-size:12px; }
.dash-tone-good { color:%GOOD_FG%; } .dash-tone-bad { color:%BAD_FG%; } .dash-tone-neutral { color:%NEUTRAL_FG%; }
.dash-tone-warn { color:%WARN_FG%; }
.dash-kpi-delta.dash-tone-good span { background:%GOOD_BG%; } .dash-kpi-delta.dash-tone-bad span { background:%BAD_BG%; }
.dash-kpi-delta.dash-tone-warn span { background:%WARN_BG%; } .dash-kpi-delta.dash-tone-neutral span { background:var(--ap-indigo-light,#eef2ff); }

/* Cards (st.container(key="dashcard_*")) share the look of the apcard_* containers */
[class*="st-key-dashcard_"] { background:%CARD_BG%; border:1px solid %CARD_BORDER% !important; border-radius:var(--ap-radius-card,12px) !important;
  box-shadow:var(--ap-shadow); padding:10px 12px; }
.dash-card-title { font-size:16px; font-weight:600; color:%TITLE%; margin:2px 0 8px; display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.dash-card-hint { font-size:12px; font-weight:400; color:%MUTED%; }
.dash-legend { display:flex; flex-direction:column; gap:2px; padding-top:6px; }
.dash-legend-row { display:flex; align-items:center; gap:8px; font-size:13px; color:%TITLE%; padding:5px 0; }
.dash-dot { width:10px; height:10px; border-radius:50%; flex:0 0 10px; }
.dash-legend-label { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dash-legend-value { color:%TITLE%; font-weight:600; font-variant-numeric:tabular-nums; }
.dash-legend-share { color:%MUTED%; width:46px; text-align:right; font-variant-numeric:tabular-nums; }
.dash-status-row { display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:1px solid %CARD_BORDER%; }
.dash-status-row:last-child { border-bottom:none; }
.dash-status-icon { width:34px; height:34px; border-radius:var(--ap-radius-control,8px); background:var(--ap-indigo-light,#eef2ff); display:flex; align-items:center; justify-content:center; flex:0 0 34px; }
.dash-status-text { flex:1; min-width:0; }
.dash-status-name { font-size:13px; font-weight:600; color:%TITLE%; }
.dash-status-detail { font-size:12px; color:%MUTED%; }
.dash-pill { font-size:12px; font-weight:600; padding:2px 10px; border-radius:var(--ap-radius-pill,9999px); white-space:nowrap; }
.dash-pill.dash-tone-good { background:%GOOD_BG%; } .dash-pill.dash-tone-warn { background:%WARN_BG%; }
.dash-pill.dash-tone-bad { background:%BAD_BG%; }
.dash-ring { display:flex; flex-direction:column; align-items:center; }
.dash-ring svg { max-width:100%; height:auto; }
.dash-ring-value { font-size:26px; font-weight:700; fill:%TITLE%; }
.dash-ring-caption { font-size:9px; fill:%MUTED%; }
.dash-ring-stats { display:flex; justify-content:space-around; width:100%; text-align:center; margin-top:8px; gap:6px; }
.dash-ring-stat-value { font-size:18px; font-weight:600; color:%TITLE%; font-variant-numeric:tabular-nums; }
.dash-ring-stat-label { font-size:12px; color:%MUTED%; }

/* Phones: one KPI card per row, tighter cards */
@media (max-width: 640px) {
  .dash-kpi-grid { grid-template-columns:1fr; gap:12px; }
  [class*="st-key-dashcard_"] { padding:8px 8px; }
  .dash-legend-row { font-size:12.5px; }
}
</style>
"""


def dashboard_css() -> str:
    """The dashboard's stylesheet with the palette filled in."""
    replacements = {
        "PAGE_BG": PAGE_BG, "TITLE": TITLE, "MUTED": MUTED, "CARD_BG": CARD_BG, "CARD_BORDER": CARD_BORDER,
        "GOOD_FG": TONES["good"][0], "GOOD_BG": TONES["good"][1], "BAD_FG": TONES["bad"][0], "BAD_BG": TONES["bad"][1],
        "WARN_FG": TONES["warn"][0], "WARN_BG": TONES["warn"][1], "NEUTRAL_FG": TONES["neutral"][0],
    }
    css = _CSS_TEMPLATE
    for name, value in replacements.items():
        css = css.replace(f"%{name}%", value)
    return css
