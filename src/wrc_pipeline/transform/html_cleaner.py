"""Extract the relevant decision content from a raw WRC HTML page.

The raw landing-zone page is a full website document (nav, header, search bar,
cookie banner, footer, sidebars). The decision text itself lives in a single
``<div class="content">`` inside the main column. We isolate that subtree, strip
any residual chrome/scripts, and emit a small, well-formed HTML document.

If the expected container is missing (layout change), we fall back to the
``<body>`` with known boilerplate removed, so the step degrades gracefully
rather than dropping content.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

# Primary container holding the decision body.
CONTENT_SELECTOR = "div.content"

# Tags that are never part of the decision content.
UNWANTED_TAGS = ["script", "style", "nav", "header", "footer", "form", "button", "noscript"]

# Boilerplate blocks identified by id/class (used in the fallback path).
UNWANTED_SELECTORS = [
    "#globalCookieBar",
    "#search",
    ".top-header",
    ".language-switch",
    ".google-translate",
    ".logo-header",
    ".searchbanner",
    ".footer-one",
    ".footer-two",
    ".social-banner",
    "#binderFixed",
]

_DOC_TEMPLATE = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    "<title>{title}</title>\n</head>\n<body>\n"
    # The decision's identifier title sits in an <h1> outside div.content on the
    # source page; re-add it so the cleaned document leads with the reference
    # (matching the "relevant content" example in the assignment screenshot).
    "<h1>{title}</h1>\n{body}\n</body>\n</html>\n"
)


def clean_html(raw: bytes, title: str = "decision") -> bytes:
    """Return cleaned, UTF-8 encoded HTML containing only the decision content."""
    soup = BeautifulSoup(raw, "lxml")

    content = soup.select_one(CONTENT_SELECTOR)
    if content is None:
        content = _fallback_body(soup)

    # Strip residual non-content elements from whatever we selected.
    for tag in content.find_all(UNWANTED_TAGS):
        tag.decompose()

    body_html = content.decode_contents().strip()
    document = _DOC_TEMPLATE.format(title=_escape(title), body=body_html)
    return document.encode("utf-8")


def _fallback_body(soup: BeautifulSoup):
    body = soup.body or soup
    for selector in UNWANTED_SELECTORS:
        for node in body.select(selector):
            node.decompose()
    return body


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
