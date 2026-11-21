"""Real-browser UI regression tests: text contrast and sidebar reachability."""
import time

import pytest

pytestmark = pytest.mark.browser

CONTRAST_JS = """
(rootSel) => {
  const root = document.querySelector(rootSel); if (!root) return {error: 'no root'};
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(',').map(s => parseFloat(s)); return {r:p[0], g:p[1], b:p[2], a: p.length>3 ? p[3] : 1}; };
  const lum = ({r,g,b}) => { const f = v => { v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0.5) return c; } return {r:255,g:255,b:255,a:1}; };
  const bad = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
    const fg = parse(cs.color); const bg = bgOf(el); if (!fg) continue;
    const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
    if (ratio < 4.5) bad.push({text: t.slice(0,40), ratio: Math.round(ratio*100)/100});
  }
  return {bad};
}
"""


def _open(browser, server_url, viewport, mobile=False):
    ctx = browser.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    page.goto(server_url)
    page.wait_for_selector("text=AnalyticsPro", timeout=30000)
    time.sleep(2)
    return ctx, page


def _sidebar_expanded(sidebar):
    """True/False from whichever attribute this Streamlit version uses (aria-expanded; data-collapsed on Streamlit 1.66.1)."""
    aria = sidebar.get_attribute("aria-expanded")
    if aria is not None:
        return aria == "true"
    collapsed = sidebar.get_attribute("data-collapsed")
    return None if collapsed is None else collapsed == "false"


def _upload(page, path):
    page.locator('input[type="file"]').first.set_input_files(path)
    page.wait_for_selector("text=Active:", timeout=30000)
    time.sleep(2)


def test_sidebar_text_has_wcag_aa_contrast_before_and_after_upload(browser, server_url, sample_csv):
    ctx, page = _open(browser, server_url, {"width": 1440, "height": 900})
    before = page.evaluate(CONTRAST_JS, '[data-testid="stSidebar"]')
    _upload(page, sample_csv)
    after = page.evaluate(CONTRAST_JS, '[data-testid="stSidebar"]')
    ctx.close()
    assert not before["bad"], f"low-contrast sidebar text (empty state): {before['bad']}"
    assert not after["bad"], f"low-contrast sidebar text (after upload): {after['bad']}"


@pytest.mark.parametrize("viewport,mobile", [
    ({"width": 1440, "height": 900}, False),
    ({"width": 390, "height": 844}, True),
])
def test_sidebar_can_be_reopened_after_closing(browser, server_url, viewport, mobile):
    ctx, page = _open(browser, server_url, viewport, mobile)
    sidebar = page.locator('[data-testid="stSidebar"]').first
    page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    time.sleep(1.5)
    assert _sidebar_expanded(sidebar) is False
    expand = page.locator('[data-testid="stExpandSidebarButton"]')
    assert expand.count() > 0 and expand.first.is_visible(), "no visible control to reopen the sidebar"
    expand.first.click()
    time.sleep(1.5)
    assert _sidebar_expanded(sidebar) is True
    ctx.close()
