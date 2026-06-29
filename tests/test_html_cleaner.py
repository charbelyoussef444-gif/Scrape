"""Tests for the HTML content extractor used by the transformation step."""

from wrc_pipeline.transform.html_cleaner import clean_html

SAMPLE = b"""
<html><body>
  <nav>NAVIGATION MENU</nav>
  <header>SITE HEADER</header>
  <div id="globalCookieBar">cookies</div>
  <div class="content">
    <h1>ADJ-00047352</h1>
    <p>The complainant was employed as a car valet.</p>
    <script>tracking()</script>
    <button>Print</button>
  </div>
  <footer>SITE FOOTER</footer>
</body></html>
"""


def test_keeps_only_decision_content():
    out = clean_html(SAMPLE, title="ADJ-00047352").decode("utf-8")
    assert "car valet" in out
    assert "ADJ-00047352" in out
    # Boilerplate and scripts are gone.
    assert "NAVIGATION MENU" not in out
    assert "SITE HEADER" not in out
    assert "SITE FOOTER" not in out
    assert "tracking()" not in out
    assert "<button" not in out


def test_fallback_when_no_content_div():
    raw = b"<html><body><nav>menu</nav><p>orphan text</p></body></html>"
    out = clean_html(raw).decode("utf-8")
    assert "orphan text" in out
    assert "menu" not in out  # nav stripped in fallback path


def test_output_is_wellformed_document():
    out = clean_html(SAMPLE).decode("utf-8")
    assert out.startswith("<!DOCTYPE html>")
    assert "<body>" in out and "</body>" in out


def test_output_leads_with_identifier_title():
    # Matches the assignment screenshot: the cleaned "relevant content" begins
    # with the decision's identifier heading.
    out = clean_html(SAMPLE, title="ADJ-00047352").decode("utf-8")
    assert "<h1>ADJ-00047352</h1>" in out
    assert out.index("<h1>ADJ-00047352</h1>") < out.index("car valet")
