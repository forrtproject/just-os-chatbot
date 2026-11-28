"""Allowlist HTML sanitizer for the answers the server sends to the page.

Python-Markdown passes raw HTML through, so an answer model (or text it quotes) could put
<script>, event handlers or javascript: links into an answer. Every answer goes through
render_markdown() or sanitize_html(): only the tags and attributes below survive, links
keep http(s):, mailto: or "#" targets, and everything else is escaped or dropped.
Stdlib only (html.parser), so it behaves the same in the CPU and GPU environments.
"""

import html
import json
import re
from html.parser import HTMLParser
from typing import List, Optional

import markdown

ALLOWED_TAGS = frozenset({
    "p", "br", "strong", "em", "b", "i", "code", "pre", "ul", "ol", "li", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td",
    "hr", "span", "a", "sup", "sub",
})
VOID_TAGS = frozenset({"br", "hr"})
# Tags dropped together with everything inside them
DROP_CONTENT_TAGS = frozenset({
    "script", "style", "iframe", "object", "noscript", "template", "svg", "math",
    "frameset", "noframes", "xmp",
})
# Every other HTML element is removed (its text kept); a "tag" that is not an HTML element, such as
# "<y [0] and z>" in "x<y [0] and z>w", was ordinary text and is shown as written (escaped).
HTML_ELEMENTS = ALLOWED_TAGS | DROP_CONTENT_TAGS | frozenset("""
    a abbr address area article aside audio base bdi bdo big blink body button canvas caption center
    cite col colgroup data datalist dd del details dfn dialog dir div dl dt embed fieldset figcaption figure
    font footer form frame head header hgroup html img input ins kbd label legend link main map mark
    marquee menu meta meter nav nobr noembed object optgroup option output param picture plaintext
    portal progress q rb rp rt rtc ruby s samp search section select slot small source strike summary
    textarea tfoot time title track tt u var video wbr image
""".split())
ALLOWED_SCHEMES = ("http://", "https://", "mailto:")
REFERENCE_CLASS = "reference-link"
# The tooltip fields qualle.ReferenceProcessor.reference_data() writes into data-reference
REFERENCE_FIELDS = frozenset({"unverified", "title", "authors", "year", "url", "text"})
# Characters browsers ignore inside a URL scheme ("java\tscript:", NUL, ...)
_URL_JUNK = re.compile(r"[\x00-\x20\x7f-\x9f]+")


def safe_href(url: Optional[str], allow_fragment: bool = False) -> Optional[str]:
    """The URL if its scheme is allowed (http, https, mailto; "#" with allow_fragment), else None."""
    if url is None:
        return None
    compact = _URL_JUNK.sub("", html.unescape(url)).lower()
    if compact.startswith(ALLOWED_SCHEMES):
        return url.strip()
    if allow_fragment and compact == "#":
        return "#"
    return None


def valid_reference_data(value: Optional[str]) -> bool:
    """True when data-reference is a JSON object with only tooltip fields and plain values
    (strings, numbers, booleans, null), as the server builds it."""
    if not value:
        return False
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(data, dict)
        and bool(data)
        and set(data) <= REFERENCE_FIELDS
        and all(v is None or isinstance(v, (str, int, float, bool)) for v in data.values())
    )


class _Sanitizer(HTMLParser):
    def __init__(self, allow_references: bool):
        super().__init__(convert_charrefs=True)
        self.allow_references = allow_references
        self.out: List[str] = []
        self.stack: List[str] = []  # open allowed tags, so the output is balanced
        self.drop_depth = 0  # inside script/style/...: drop everything

    # -- tags ---------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, closed=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, closed=True)

    def _start(self, tag, attrs, closed):
        if tag in DROP_CONTENT_TAGS:
            if not closed:
                self.drop_depth += 1
            return
        if self.drop_depth:
            return
        if tag not in HTML_ELEMENTS:
            self.out.append(html.escape(self.get_starttag_text() or "", quote=False))
            return
        if tag not in ALLOWED_TAGS:
            return
        kept = self._attributes(tag, attrs)
        text = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in kept)
        self.out.append(f"<{tag}{text}>")
        if tag not in VOID_TAGS:
            if closed:
                self.out.append(f"</{tag}>")
            else:
                self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if self.drop_depth:
            return
        if tag not in HTML_ELEMENTS:
            self.out.append(html.escape(f"</{tag}>", quote=False))
            return
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag not in self.stack:
            return  # stray end tag
        while self.stack:
            open_tag = self.stack.pop()
            self.out.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def _attributes(self, tag, attrs):
        attrs = {name: value for name, value in attrs if value is not None}
        kept = []
        # A citation link keeps href="#", its class and data-reference only when the data is valid
        # tooltip JSON; otherwise it is an ordinary link and loses all three
        is_reference = (
            self.allow_references
            and tag == "a"
            and (attrs.get("class") or "").strip() == REFERENCE_CLASS
            and valid_reference_data(attrs.get("data-reference"))
        )
        if tag == "a":
            href = safe_href(attrs.get("href"), allow_fragment=is_reference)
            if href is not None:
                kept.append(("href", href))
            if is_reference:
                kept.append(("class", REFERENCE_CLASS))
                kept.append(("data-reference", attrs["data-reference"]))
            if attrs.get("title"):
                kept.append(("title", attrs["title"]))
        elif tag in ("th", "td"):
            for name in ("colspan", "rowspan"):
                if (attrs.get(name) or "").isdigit():
                    kept.append((name, attrs[name]))
        elif tag == "ol" and (attrs.get("start") or "").isdigit():
            kept.append(("start", attrs["start"]))
        return kept

    # -- text ---------------------------------------------------------------
    def handle_data(self, data):
        if not self.drop_depth:
            self.out.append(html.escape(data, quote=False))

    # Comments, <!DOCTYPE>, <?pi?> and CDATA are dropped
    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass

    def result(self) -> str:
        self.close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def sanitize_html(text: str, allow_references: bool = False) -> str:
    """Keep only allowlisted tags and attributes. With allow_references, <a class="reference-link"
    href="#" data-reference="..."> (the citation links the server builds) keep their attributes when
    data-reference is valid tooltip JSON (valid_reference_data); without it, such links lose them."""
    parser = _Sanitizer(allow_references)
    parser.feed(text or "")
    return parser.result()


def render_markdown(text: str, extensions: Optional[list] = None) -> str:
    """Markdown -> sanitized HTML (no citation links: those are added by the reference processor)."""
    return sanitize_html(markdown.markdown(text or "", extensions=extensions or []))
