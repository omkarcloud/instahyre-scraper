"""/instahyre/companies/* — company pages (ratings, benefits, tech stack,
socials, office photos, open jobs), a company's job listing and the company
name search.

A `company` param arrives resolved by refs.resolve_company: an employer id
(the number on every logo / API path), a /jobs-at-<slug>/ page slug or link
(resolved to the id through the page's inline employerId), or a name that
is looked up through the site's own company suggestions (exact match first,
else the first hit)."""
from instahyre import cache_config as ttl
from instahyre import fetch, refdata
from instahyre import parsers as P


def _workers():
    try:
        import config
        return int(config.INSTAHYRE_WORKERS)
    except Exception:
        return 4


# ---- resolving --------------------------------------------------------------------------------------------

def search(query, limit=10):
    """Companies whose name matches `query` (the site's own suggestions)."""
    rows = fetch.autocomplete_companies(query)
    companies = [P.company_suggestion(r) for r in rows if isinstance(r, dict)][:limit]
    return {"query": query, "companies": companies, "count": len(companies)}


def resolve_id(company):
    """A resolved `company` ref -> its employer id (a slug is read off its
    page, a name looked up on the site; both memoised + cached)."""
    if company.get("id") is not None:
        return int(company["id"])
    if company.get("slug"):
        slug = company["slug"]
        return fetch.shared_raw("company_id_by_slug", {"slug": slug},
                                lambda: fetch.company_page_employer_id(slug), ttl.COMPANY_ID_CACHE)
    name = company["name"]

    def build():
        hits = [P.company_suggestion(r) for r in fetch.autocomplete_companies(name) if isinstance(r, dict)]
        exact = [c for c in hits if (c.get("name") or "").lower() == name.lower()]
        hit = (exact or hits or [None])[0]
        if not hit or not hit.get("id"):
            raise fetch.InstahyreNotFound(f"Instahyre has no company named {name!r}")
        return hit["id"]
    return fetch.shared_raw("company_id_by_name", {"name": name.lower()}, build, ttl.COMPANY_ID_CACHE)


# ---- profiles ----------------------------------------------------------------------------------------------

def profile(employer_id, with_counts=True):
    """The parsed company page of an employer id (+ its per-category job
    counts, a second call made in parallel)."""
    def page():
        return fetch.employer(employer_id)

    def counts():
        return fetch.employer_job_counts(employer_id) if with_counts else None

    outcomes = fetch.run_parallel([page, counts], 2)
    status, raw = outcomes[0]
    if status == "error":
        raise raw
    if not isinstance(raw, dict) or not raw.get("company_name"):
        raise fetch.InstahyreNotFound(f"Instahyre has no company with the id {employer_id}")
    c_status, c_value = outcomes[1]
    if c_status == "error":
        print(f"instahyre: job counts of company {employer_id} skipped: {c_value}")
        c_value = None
    return P.employer_profile(raw, c_value if with_counts else None, employer_id=employer_id)


def details(company, include_jobs=True):
    """The company page: identity, about / why-us, headquarters, industries,
    website and socials, Glassdoor ratings, benefits, tech stack, office
    photos, open-job count by category and (include_jobs) the page's first
    open jobs."""
    employer_id = resolve_id(company)
    out = profile(employer_id)
    if not include_jobs:
        out["jobs"] = None
    return out


def open_jobs(company, page=1, query=None, location=None, job_type=None, experience_years=None):
    """One page (35) of a company's open jobs through the job search's
    company filter (the page itself lists only ten), with the search filters."""
    from instahyre import jobs as J
    employer_id = resolve_id(company)
    head = profile(employer_id, with_counts=False)
    name = head.get("name")
    result = J.search(query=query, location=location, experience_years=experience_years, job_type=job_type,
                      company=[name], page=page)
    result["company"] = {"id": head.get("id"), "name": name, "slug": head.get("slug"), "link": head.get("link"),
                         "logo": head.get("logo"), "jobs_count": head.get("jobs_count")}
    return result
