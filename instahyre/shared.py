"""Value helpers shared by every Instahyre parser: safe nested access,
numbers, text, dates, site links and HTML descriptions. Pure functions, no
network; every helper tolerates None and junk.

The generic helpers (g / as_list / as_dict, num … iso_date, html_to_text) have
the same semantics as seek/shared.py and jobstreet/shared.py; the ones every
site shares come from scraper_utils and the rest live here (the instahyre
package ships as its own open-source repo, which must not pull in other sites'
modules)."""
import html as html_lib
import re
from datetime import datetime
from html.parser import HTMLParser

from instahyre import refdata
from scraper_utils.values import as_dict, as_list, count, g, num, rating, to_int_round as to_int, year
from scraper_utils.text import clean as text, html_to_text, text_list
from scraper_utils.dates import iso_date

# ---- text ----------------------------------------------------------------------------------


def multiline(value):
    """Like text() but keeps line breaks (descriptions)."""
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


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


def html_fragment(value):
    """The site wraps rich text in '<html><body>…</body></html>'; keep the
    inner fragment. '' / None -> None."""
    value = value if isinstance(value, str) else None
    if not value or not value.strip():
        return None
    out = re.sub(r"^\s*<html>\s*<body>\s*", "", value, flags=re.I)
    out = re.sub(r"\s*</body>\s*</html>\s*$", "", out, flags=re.I).strip()
    return out or None
