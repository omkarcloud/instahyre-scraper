"""Instahyre transport: plain curl_cffi, no browser, validated 2026-10-19
from a direct India egress with no cookies and no login.

Surfaces (all on www.instahyre.com, the JSON ones with a same-origin
Referer — the site's own Angular app calls them anonymously):

  job_search(params)             /api/v1/job_search/ — the search behind
                                 /search-jobs/: 35 cards a call whatever
                                 `limit` says, offset + 35 <= 10,000, every
                                 filter the site has (skills free text,
                                 jobLocations, years, job_type, company_size,
                                 job_functions / job_categories /
                                 industry_types ids, companies names; repeat
                                 a key for several values, never commas) and
                                 the facet counts in `meta`.
  job_detail(id)                 /api/v1/employer_public_jobs/<id> — the
                                 full ad: description, experience band,
                                 category, functions, recruiter, internship
                                 stipend, is_active (closed ads still answer).
  job_page(path)                 the /job-<id>-…/ HTML page — only for its
                                 JSON-LD JobPosting (datePosted, the state of
                                 every city, the employer's website): the
                                 only place the posting date exists.
  employer(id)                   /api/v1/brand_page/brand_page_employer/<id>
                                 — the company page: Glassdoor ratings,
                                 benefits, tech stack, summary, socials,
                                 office photos, open-job count + first jobs.
  employer_job_counts(id)        …/brand_page_employer/get_jobs_list_count/
  similar_jobs(id)               /api/v1/brand_page/similar_jobs?job_id=
  job_functions() / industry_types() / location_data()
                                 the three lookup lists
  autocomplete_*(query)          the search box suggestions (locations,
                                 companies, skills)
  company_page(slug)             the /jobs-at-<slug>/ HTML page — only to
                                 read the employer id a slug maps to.

Egress: direct by default (config.INSTAHYRE_PROXY_COUNTRY None). The site
rate-limits the search API per IP (HTTP 429 after ~50 calls in a minute,
clears within a minute); a 429 / 403 / 5xx is retried on a fresh sticky
residential exit (config.instahyre_proxy(fallback=True)). No Cloudflare
challenge was seen on any surface, HTML pages included; the patchright
click-through (indeed/fetch.py _browser_page) is the escalation if that
changes — not built while plain HTTP works.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  InstahyreUpstreamError  transport failure / 5xx / unexpected body — retryable
  InstahyreBlocked        429 / 403 / challenge                     — retryable on a new exit
  InstahyreBadRequest     the site rejected the params (400)        — never retried
  InstahyreNotFound       no such job / company                     — never retried
"""
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from instahyre import refdata

IMPERSONATE = "chrome"
TIMEOUT = (10, 40)            # (connect, read)

JSON_HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9",
                "referer": refdata.SEARCH_REFERER, "x-requested-with": "XMLHttpRequest"}
HTML_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9"}
CF_MARKERS = ("just a moment", "challenge-error-text", "cf-chl", "challenge-platform", "attention required")

SEARCH_PATH = "/api/v1/job_search/"
JOB_PATH = "/api/v1/employer_public_jobs/{id}"
EMPLOYER_PATH = "/api/v1/brand_page/brand_page_employer/{id}"
EMPLOYER_COUNTS_PATH = "/api/v1/brand_page/brand_page_employer/get_jobs_list_count/"
SIMILAR_PATH = "/api/v1/brand_page/similar_jobs"
JOB_FUNCTIONS_PATH = "/api/v1/job_function/"
INDUSTRIES_PATH = "/api/v1/industry_type/"
LOCATIONS_PATH = "/api/v1/candidate_misc/profile/candidate_locations/location_data/"
LOCATION_SUGGEST_PATH = "/api/v1/candidate_misc/profile/candidate_locations/autocomplete/"
COMPANY_SUGGEST_PATH = "/api/v1/employer_misc/employer_profile/anon_employer_limited/autocomplete/"
SKILL_SUGGEST_PATH = "/api/v1/job_form/agency_skill/"


class InstahyreUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class InstahyreBlocked(InstahyreUpstreamError, Blocked):
    """429 / 403 / challenge — retryable on a fresh exit."""


class InstahyreBadRequest(BadRequest):
    """The site rejected the params — never retried."""


class InstahyreNotFound(NotFound):
    """No such job / company — never retried."""


def dump_debug(name, text):
    """Write a raw response to $INSTAHYRE_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("INSTAHYRE_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()


def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store


def _session(key, proxy):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _attempts(label, send):
    """Run send(session) under the retry policy: InstahyreUpstreamError (incl.
    Blocked) retries on a fresh exit up to config.INSTAHYRE_MAX_ATTEMPTS
    times; BadRequest / NotFound surface at once."""
    attempts = max(1, int(config.INSTAHYRE_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        proxy = config.instahyre_proxy(fallback=attempt > 1)
        key = f"{attempt if proxy else 0}:{proxy or 'direct'}"
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (InstahyreBadRequest, InstahyreNotFound):
            raise
        except InstahyreUpstreamError as e:
            last = e
        except Exception as e:
            last = InstahyreUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
        _drop_session(key)
        print(f"instahyre: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(1.0 * attempt)
    raise last


def is_challenged(status, headers, text):
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


def _bad_request_message(text):
    """The API's 400 body is {"<field>": ["message"]} or {"error": "…"}."""
    try:
        body = json.loads(text)
    except ValueError:
        return (text or "")[:200]
    if isinstance(body, dict):
        parts = []
        for key, value in body.items():
            msgs = value if isinstance(value, list) else [value]
            parts.append(f"{key}: {' '.join(str(m) for m in msgs)}")
        return "; ".join(parts)[:300]
    return str(body)[:200]


def _classify(resp, label, json_body=True):
    """Raise the failure a response represents, else return its JSON (or text)."""
    status = resp.status_code
    headers = dict(resp.headers)
    text = resp.text or ""
    if is_challenged(status, headers, text):
        dump_debug("challenged", text)
        raise InstahyreBlocked(f"challenge (HTTP {status}) on {label}")
    if status in (403, 429):
        raise InstahyreBlocked(f"HTTP {status} on {label}")
    if status in (404, 410):
        raise InstahyreNotFound(f"Instahyre has no page for {label}")
    if status == 400:
        raise InstahyreBadRequest(f"Instahyre rejected the request on {label}: {_bad_request_message(text)}")
    if status >= 500:
        raise InstahyreUpstreamError(f"HTTP {status} on {label}")
    if status != 200:
        raise InstahyreUpstreamError(f"HTTP {status} on {label}")
    if not json_body:
        return text
    try:
        return json.loads(text)
    except ValueError:
        dump_debug("non_json", text)
        raise InstahyreUpstreamError(f"non-JSON answer on {label}")


def api_get(path, params=None, label=None, expect=dict):
    """GET one JSON endpoint on the site -> its parsed body (`expect` = the
    body type: dict / list)."""
    query = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    url = f"{refdata.BASE_URL}{path}" + (f"?{urlencode(query, doseq=True)}" if query else "")
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=JSON_HEADERS, timeout=TIMEOUT)
        body = _classify(resp, label)
        if expect is not None and not isinstance(body, expect):
            dump_debug("unexpected", resp.text)
            raise InstahyreUpstreamError(f"unexpected payload on {label}")
        return body
    return _attempts(label, send)


def html_get(path, label=None):
    """GET one HTML page on the site -> its text."""
    url = path if path.startswith("http") else f"{refdata.BASE_URL}{path}"
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=HTML_HEADERS, timeout=TIMEOUT)
        return _classify(resp, label, json_body=False)
    return _attempts(label, send)


# ---- jobs ------------------------------------------------------------------------------------------

def job_search(params, label="job search"):
    """GET the job-search API with `params` (the site's own names; list
    values repeat the key) -> {"objects": [...], "meta": {...}}."""
    query = dict(params or {})
    query.setdefault("limit", refdata.PAGE_SIZE)
    query.setdefault("search", "true")
    body = api_get(SEARCH_PATH, query, label)
    if not isinstance(body.get("objects"), list):
        raise InstahyreUpstreamError(f"unexpected job-search payload on {label}")
    return body


def job_detail(job_id):
    """The public job record; InstahyreNotFound when the id does not exist
    (closed ads still answer, with is_active false)."""
    return api_get(JOB_PATH.format(id=job_id), label=f"job {job_id}")


def job_page(path, label=None):
    """The job's HTML page (for its JSON-LD JobPosting)."""
    return html_get(path, label or f"job page {path}")


def similar_jobs(job_id):
    body = api_get(SIMILAR_PATH, {"job_id": job_id}, label=f"similar jobs of {job_id}")
    return body.get("objects") if isinstance(body.get("objects"), list) else []


# ---- employers -------------------------------------------------------------------------------------

def employer(employer_id):
    """The company (brand) page record."""
    return api_get(EMPLOYER_PATH.format(id=employer_id), label=f"company {employer_id}")


def employer_job_counts(employer_id):
    body = api_get(EMPLOYER_COUNTS_PATH, {"id": employer_id}, label=f"job counts of company {employer_id}")
    return body.get("job_categories") if isinstance(body.get("job_categories"), list) else []


_EMPLOYER_ID_RE = re.compile(r"employerId\s*=\s*['\"](\d+)['\"]")


def company_page_employer_id(slug):
    """The employer id of a /jobs-at-<slug>/ page (the page's inline
    `employerId` variable); InstahyreNotFound when the slug has no page."""
    html = html_get(f"/jobs-at-{slug}/", label=f"company page {slug}")
    match = _EMPLOYER_ID_RE.search(html or "")
    if not match or not int(match.group(1)):
        raise InstahyreNotFound(f"Instahyre has no company page for the slug {slug!r}")
    return int(match.group(1))


# ---- lookups ---------------------------------------------------------------------------------------

def job_functions():
    body = api_get(JOB_FUNCTIONS_PATH, label="job functions")
    return body.get("objects") if isinstance(body.get("objects"), list) else []


def industry_types():
    body = api_get(INDUSTRIES_PATH, label="industry types")
    return body.get("objects") if isinstance(body.get("objects"), list) else []


def location_data():
    """{"cities_current": [...], "cities_preferred": [...], ...groups} — the
    location picker (cities_current includes the remote entry)."""
    body = api_get(LOCATIONS_PATH, label="locations")
    data = body.get("data")
    if not isinstance(data, dict):
        raise InstahyreUpstreamError("unexpected locations payload")
    return data


def _suggest(path, params, label):
    body = api_get(path, params, label)
    return body.get("objects") if isinstance(body.get("objects"), list) else []


def autocomplete_locations(query):
    return _suggest(LOCATION_SUGGEST_PATH, {"name": query}, f"location suggestions {query!r}")


def autocomplete_companies(query):
    return _suggest(COMPANY_SUGGEST_PATH, {"company": query}, f"company suggestions {query!r}")


def autocomplete_skills(query):
    return _suggest(SKILL_SUGGEST_PATH, {"skills": query}, f"skill suggestions {query!r}")


# ---- memo / cache / parallel ---------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def shared_raw(name, params, build, ttl):
    """An upstream payload shared by several routes: in-process memo, then
    the service's response cache (pods share it) when one is installed,
    then build(). Without a `cache` module (the standalone package) it is
    the in-process memo alone."""
    try:
        from cache import cached_call
    except ImportError:
        cached_call = None
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = (name, json.dumps(params, sort_keys=True))
    if cached_call is None:
        return memoized(key, build, ttl=min(seconds, MEMO_TTL))
    return memoized(key, lambda: cached_call(f"instahyre.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    # Smoke test: python instahyre/fetch.py
    body = job_search({"skills": "python", "jobLocations": "Bangalore"})
    print("search:", body["meta"].get("total_count"), [j.get("title") for j in body["objects"][:3]])
    job_id = body["objects"][0]["id"]
    detail = job_detail(job_id)
    print("job:", detail.get("title"), detail.get("workex_min"), detail.get("workex_max"))
    emp = employer(body["objects"][0]["employer"]["id"])
    print("company:", emp.get("company_name"), emp.get("jobs_count"), emp.get("glassdoor_data"))
