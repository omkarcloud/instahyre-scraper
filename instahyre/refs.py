"""Instahyre input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  job           446555 | https://www.instahyre.com/job-446555-software-engineer-at-x-bangalore/
                | job-446555-software-engineer-…                         -> 446555
  company       35927 | https://www.instahyre.com/jobs-at-axiamatic-2/ | jobs-at-axiamatic-2
                | Axiamatic (a name, looked up on the site at call time)
                                        -> {"id": 35927, "slug": None, "name": None}
                                         | {"id": None, "slug": "axiamatic-2", "name": None}
                                         | {"id": None, "slug": None, "name": "Axiamatic"}
  location      Bangalore | bengaluru | remote | Delhi NCR | Pune, Mumbai
                                        -> ["Bangalore"] / ["Work From Home"] / ["Delhi / NCR"] / ["Pune", "Mumbai"]
                (the site's own picker values, matched case-insensitively on
                 the value, the display name and the alternate spellings)
  job_function  backend-development | 10 | Backend Development (comma list)  -> [10]
  job_category  software-engineering | 1 | Software Engineering (comma list) -> [1]
  industry      13 | Computer Software / IT / Internet (comma list)          -> [13]
  company_names (search filter) free text names, comma list                  -> ["Amazon", "Accenture"]
"""
import re
from urllib.parse import unquote, urlparse

from instahyre import refdata

_SLUG_BAD = re.compile(r"[/?#\\<>\"]")
_HOST_RE = re.compile(r"(?:^|\.)instahyre\.com$")


def _parse_url(value):
    """-> (host, path) when value looks like an Instahyre URL or host path,
    None when it is plain text. Raises ValueError for another site."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if not _HOST_RE.search(head):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not _HOST_RE.search(host):
        raise ValueError("Must be an instahyre.com link.")
    return host, unquote(parsed.path)


def _split(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


# ---- jobs -------------------------------------------------------------------------------------------

JOB_HINT = ("Must be an Instahyre job id (digits, e.g. 446555) or a job link "
            "(https://www.instahyre.com/job-446555-software-engineer-at-acme-bangalore/).")


def resolve_job(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    path = url[1] if url else raw
    match = re.search(r"(?:^|/)job-(\d+)(?:-|/|$)", path)
    if match:
        return int(match.group(1))
    raise ValueError(JOB_HINT)


def resolve_jobs(value, limit=refdata.MAX_BATCH):
    """'446555, https://www.instahyre.com/job-440752-…/' -> [446555, 440752] (deduped, 1..limit)."""
    out = []
    for item in _split(value):
        job_id = resolve_job(item)      # ValueError carries the hint
        if job_id not in out:
            out.append(job_id)
    if not out:
        raise ValueError("Must list at least one job id or link (comma-separated).")
    if len(out) > limit:
        raise ValueError(f"At most {limit} jobs.")
    return out


# ---- companies ----------------------------------------------------------------------------------------

COMPANY_HINT = ("Must be a company id (35927), a company page link or slug "
                "(https://www.instahyre.com/jobs-at-axiamatic-2/, jobs-at-axiamatic-2) or a company name.")


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    if raw.isdigit():
        return {"id": int(raw), "slug": None, "name": None}
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        match = re.search(r"/jobs-at-([^/?#]+)", url[1])
        if not match:
            raise ValueError("Links must be company pages (https://www.instahyre.com/jobs-at-<company>/).")
        return {"id": None, "slug": match.group(1).lower(), "name": None}
    match = re.fullmatch(r"jobs-at-([a-z0-9][a-z0-9-]*)/?", raw.lower())
    if match:
        return {"id": None, "slug": match.group(1), "name": None}
    name = " ".join(raw.split())
    if _SLUG_BAD.search(name) or len(name) > 150:
        raise ValueError(COMPANY_HINT)
    return {"id": None, "slug": None, "name": name}


def resolve_company_names(value, limit=10):
    """The search's company filter: exact company names as the site lists
    them ('Amazon, Accenture') -> ['Amazon', 'Accenture']."""
    out = []
    for item in _split(value):
        name = " ".join(item.split())
        if _SLUG_BAD.search(name) or len(name) > 150:
            raise ValueError(f"'{item}' is not a company name.")
        if name not in out:
            out.append(name)
    if len(out) > limit:
        raise ValueError(f"At most {limit} companies.")
    return out or None


# ---- locations ----------------------------------------------------------------------------------------------

_LOCATION_ALIASES = {
    "remote": refdata.REMOTE_LOCATION, "wfh": refdata.REMOTE_LOCATION, "work from home": refdata.REMOTE_LOCATION,
    "work from home / remote": refdata.REMOTE_LOCATION, "anywhere": "Anywhere in India", "india": "Anywhere in India",
    "ncr": refdata.DELHI_NCR, "delhi ncr": refdata.DELHI_NCR, "delhi-ncr": refdata.DELHI_NCR,
    "delhi/ncr": refdata.DELHI_NCR,
}


def _location_index(table=None):
    """lower-cased value / display name / alternate spelling -> picker value."""
    index = dict(_LOCATION_ALIASES)
    for value, (name, _group, alternates) in (table or refdata.LOCATIONS).items():
        for key in [value, name, *alternates]:
            key = " ".join(str(key or "").lower().split())
            if key:
                index.setdefault(key, value)
    return index


_INDEX = None


def location_index(table=None):
    """The static index (cached) or one over a live table."""
    global _INDEX
    if table is not None:
        return _location_index(table)
    if _INDEX is None:
        _INDEX = _location_index()
    return _INDEX


LOCATION_HINT = ("Must be a city or region as Instahyre lists it (Bangalore, Pune, Delhi / NCR, "
                 "South India, Work From Home / remote); see /instahyre/locations.")


def resolve_locations(value, limit=10, table=None):
    """'Bangalore, bengaluru, remote' -> ['Bangalore', 'Work From Home'] (the
    picker values the search API accepts, deduped, 1..limit)."""
    index = location_index(table)
    out = []
    for item in _split(value):
        key = " ".join(item.lower().split())
        canonical = index.get(key)
        if canonical is None:
            raise ValueError(f"'{item}' is not a location Instahyre knows. " + LOCATION_HINT)
        if canonical not in out:
            out.append(canonical)
    if len(out) > limit:
        raise ValueError(f"At most {limit} locations.")
    return out or None


# ---- taxonomies ---------------------------------------------------------------------------------------------

def _resolve_taxonomy(value, index, kind, hint, limit=10):
    out = []
    items = _split(value)
    i = 0
    while i < len(items):
        # a name with a comma in it ('Accounting, Finance & Banking') spans two items
        for step in (1, 2):
            ident = index.get(" ".join(", ".join(items[i:i + step]).lower().split())) if i + step <= len(items) else None
            if ident is not None:
                break
        if ident is None:
            raise ValueError(f"'{items[i]}' is not a {kind} id, slug or name; see {hint}.")
        if ident not in out:
            out.append(ident)
        i += step
    if len(out) > limit:
        raise ValueError(f"At most {limit} values.")
    return out or None


def _function_index():
    index = {}
    for fid, (slug, name, _cat) in refdata.JOB_FUNCTIONS.items():
        index[str(fid)] = fid
        index[slug.lower()] = fid
        index[" ".join(name.lower().split())] = fid
    return index


def _category_index():
    index = {}
    for cid, (name, _tech) in refdata.JOB_CATEGORIES.items():
        index[str(cid)] = cid
        index[" ".join(name.lower().split())] = cid
        index[re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")] = cid
    return index


def _industry_index():
    index = {}
    for iid, name in refdata.INDUSTRIES.items():
        index[str(iid)] = iid
        index[" ".join(name.lower().split())] = iid
        index[re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")] = iid
    return index


def resolve_job_functions(value):
    return _resolve_taxonomy(value, _function_index(), "job function", "/instahyre/job-functions")


def resolve_job_categories(value):
    return _resolve_taxonomy(value, _category_index(), "job category", "/instahyre/job-functions")


def resolve_industries(value):
    return _resolve_taxonomy(value, _industry_index(), "industry", "/instahyre/industries")


def slugify(value):
    """'Software Engineering' -> 'software-engineering'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or None
