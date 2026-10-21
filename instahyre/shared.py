"""Value helpers shared by every Instahyre parser: safe nested access,
numbers, text, dates, site links and HTML descriptions. Pure functions, no
network; every helper tolerates None and junk.

The generic helpers (g / as_list / as_dict, num … iso_date, html_to_text)
have the same semantics as seek/shared.py and jobstreet/shared.py; they live
here so the instahyre package stands alone (it ships as its own open-source
repo, which must not pull in other sites' modules)."""
import html as html_lib
import re
from datetime import datetime
from html.parser import HTMLParser

from instahyre import refdata

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- numbers -------------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def count(value):
    """A non-negative count; negatives (the site's 'none' markers) -> 0."""
    out = to_int(value)
    if out is None:
        return None
    return out if out >= 0 else 0


def rating(value):
    """A 0-5 star rating rounded to 2 places; 0 / missing -> None."""
    out = num(value)
    return round(out, 2) if out else None


def year(value):
    """A founding year: 4-digit int, else None (the site stores 0 for unknown)."""
    out = to_int(value)
    return out if out and 1000 <= out <= 2100 else None


# ---- text ----------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None."""
    if value is None or isinstance(value, bool):
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (descriptions)."""
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


def text_list(values):
    """A list of strings, trimmed, deduped, empties dropped."""
    out = []
    for value in as_list(values):
        item = text(value)
        if item and item not in out:
            out.append(item)
    return out


def split_csv(value):
    """The search card's 'Bangalore,Gurgaon' location string -> ['Bangalore', 'Gurgaon']."""
    if isinstance(value, list):
        return text_list(value)
    value = text(value)
    if not value:
        return []
    return text_list(value.split(","))


def lower_snake(value):
    """'Work-Life Balance' -> 'work_life_balance'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


_LONG_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y")


def iso_date(value):
    """'2026-10-12' / '2026-10-12T…' / 'October 12, 2026' -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ---- links -------------------------------------------------------------------------------

def link(path):
    """A site-relative path (or absolute URL) -> absolute https link; '' / None -> None."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"{refdata.BASE_URL}/{path.lstrip('/')}"


def company_link(slug):
    return f"{refdata.BASE_URL}/jobs-at-{slug}/" if slug else None


def id_from_uri(value):
    """'/api/v1/job_function/10' / 10 -> 10 (the trailing numeric id of a resource uri)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    value = text(value)
    if not value:
        return None
    match = re.search(r"(\d+)/?$", value)
    return int(match.group(1)) if match else None


def job_id_from_link(value):
    """'https://www.instahyre.com/job-446555-software-engineer-at-x-bangalore/' -> 446555."""
    value = text(value)
    if not value:
        return None
    match = re.search(r"/job-(\d+)-", value)
    return int(match.group(1)) if match else None


def is_remote(locations):
    return any(loc.lower() in ("work from home", "remote", "work from home / remote") for loc in as_list(locations))


# ---- HTML -> text ------------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None


def html_fragment(value):
    """The site wraps rich text in '<html><body>…</body></html>'; keep the
    inner fragment. '' / None -> None."""
    value = value if isinstance(value, str) else None
    if not value or not value.strip():
        return None
    out = re.sub(r"^\s*<html>\s*<body>\s*", "", value, flags=re.I)
    out = re.sub(r"\s*</body>\s*</html>\s*$", "", out, flags=re.I).strip()
    return out or None
