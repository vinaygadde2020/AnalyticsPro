"""Release-validation regressions: bugs found by rendering the app in a real browser (final integration phase).

Each test fails on the Stage 4 code and passes after the fix.
"""
import re

from streamlit.testing.v1 import AppTest

from tests.conftest import APP_PATH, APPTEST_TIMEOUT
from views.common import build_global_css


def test_empty_state_card_title_is_escaped_exactly_once():
    """The card title was written as `&amp;` and then escaped again, so the page showed the literal text 'Ask &amp; export'."""
    at = AppTest.from_file(APP_PATH, default_timeout=APPTEST_TIMEOUT).run()
    assert not at.exception
    html = "\n".join(m.value for m in at.markdown)
    assert "&amp;amp;" not in html
    assert "Ask &amp; export" in html  # single escape == renders as 'Ask & export'


def test_sidebar_reset_button_has_its_own_readable_style():
    """The reset button has a help tooltip (extra wrapper spans), so the generic `.stButton > button` rule never reached it
    and it rendered light text on Streamlit's light default background (contrast 1.41:1)."""
    css = build_global_css()
    rules = re.findall(r'\[data-testid="stSidebar"\] \[class\*="st-key-reset_dataset_btn"\] button \{([^}]*)\}', css)
    assert rules, "no rule for the sidebar reset button"
    assert any("background: transparent" in r and "color: var(--ap-sidebar-text)" in r for r in rules), "reset button never gets a readable background/colour"


def test_topbar_makes_room_for_the_expand_button_with_either_sidebar_attribute():
    """Streamlit 1.66 marks the sidebar with data-collapsed (older versions used aria-expanded); both must reserve space."""
    css = build_global_css()
    assert '[data-collapsed="true"]' in css and '[aria-expanded="false"]' in css
    assert "padding-left: 3.25rem" in css
