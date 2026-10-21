"""/instahyre/jobs/* — job search (+ its facet stats), job details, batch
lookup and similar jobs, from the site's own job-search API, the public job
record, the job page's JSON-LD (posting date) and the company page."""
from instahyre import cache_config as ttl
from instahyre import fetch, refdata
from instahyre import parsers as P


def _workers():
    try:
        import config
        return int(config.INSTAHYRE_WORKERS)
    except Exception:
        return 4


def search_params(query=None, location=None, experience_years=None, job_type=None, company_size=None,
                  job_function=None, job_category=None, industry=None, company=None, page=1):
    """Public params -> the search API's own query (its names and codes).
    List values are sent as repeated keys (the API refuses commas)."""
    return {
        "skills": query,
        "jobLocations": location or None,
        "years": experience_years,
        "job_type": refdata.JOB_TYPES.get(job_type) if job_type else None,
        "company_size": refdata.COMPANY_SIZES.get(company_size) if company_size else None,
        "job_functions": job_function or None,
        "job_categories": job_category or None,
        "industry_types": industry or None,
        "companies": company or None,
        "offset": (max(1, page) - 1) * refdata.PAGE_SIZE,
    }


def _filters(query, location, experience_years, job_type, company_size, job_function, job_category, industry, company):
    return {
        "query": query,
        "locations": location,
        "experience_years": experience_years,
        "job_type": job_type,
        "company_size": company_size,
        "job_functions": [P.job_function_ref(f) for f in (job_function or [])] or None,
        "job_categories": [{"id": c, "name": (refdata.JOB_CATEGORIES.get(c) or (None,))[0]} for c in (job_category or [])] or None,
        "industries": [{"id": i, "name": refdata.INDUSTRIES.get(i)} for i in (industry or [])] or None,
        "companies": company,
    }


def search(query=None, location=None, experience_years=None, job_type=None, company_size=None, job_function=None,
           job_category=None, industry=None, company=None, page=1, include_details=False):
    """One page (35 cards, the site's fixed page size) of the job search with
    the facet counts. The site serves at most the first 10,000 results of a
    filter combination (page 285). With include_details every card also
    carries its job record (description, experience band, functions,
    recruiter, internship terms) — 35 extra calls, fetched in parallel."""
    if page > refdata.MAX_PAGE:
        raise ValueError(f"Instahyre serves at most {refdata.RESULT_WINDOW} results per search "
                         f"(page {refdata.MAX_PAGE}); narrow the filters instead.")
    params = search_params(query, location, experience_years, job_type, company_size, job_function, job_category,
                           industry, company, page)
    raw = fetch.job_search(params, label=f"job search {query!r} p{page}")
    result = P.search_result(raw, page)
    if include_details and result["jobs"]:
        ids = [card["id"] for card in result["jobs"]]
        outcomes = fetch.run_parallel([lambda i=i: _detail(i) for i in ids], _workers())
        cards = []
        for card, (status, value) in zip(result["jobs"], outcomes):
            cards.append(P.merge_card_details(card, value if status == "ok" else None))
        result["jobs"] = cards
    result["filters"] = _filters(query, location, experience_years, job_type, company_size, job_function,
                                 job_category, industry, company)
    return result


def stats(query=None, location=None, experience_years=None, job_type=None, company_size=None, job_function=None,
          job_category=None, industry=None, company=None):
    """The size of a search and its facet breakdown (job types, company
    sizes, top functions / industries / companies / locations) — one call,
    no cards."""
    params = search_params(query, location, experience_years, job_type, company_size, job_function, job_category,
                           industry, company, 1)
    raw = fetch.job_search(params, label=f"job stats {query!r}")
    result = P.search_result(raw, 1)
    return {
        "total_count": result["pagination"]["total_count"],
        "is_count_exact": result["is_count_exact"],
        "facets": result["facets"],
        "filters": _filters(query, location, experience_years, job_type, company_size, job_function, job_category,
                            industry, company),
    }


# ---- details ------------------------------------------------------------------------------------------------

def _detail(job_id):
    """The job record parsed on its own (no page, no company)."""
    raw = fetch.job_detail(job_id)
    result = P.job_details(raw)
    if result is None:
        raise fetch.InstahyreNotFound(f"Instahyre has no job with the id {job_id}")
    return result


def details(job, include_company=True):
    """The full ad: description, experience band, category and functions,
    recruiter, internship terms, posting date (from the job page's JSON-LD)
    and, with include_company, the company page (ratings, benefits, tech
    stack, socials, headquarters). 404 when the site has no such job; closed
    ads still come back with is_active false and no posting date."""
    raw = fetch.job_detail(job)
    if not isinstance(raw, dict) or raw.get("id") is None:
        raise fetch.InstahyreNotFound(f"Instahyre has no job with the id {job}")
    path = raw.get("opportunity_url")
    employer_id = _employer_id_of(raw)

    def page():
        if not path:
            return None
        try:
            return P.job_posting_ld(fetch.job_page(path, label=f"job page {job}"))
        except fetch.InstahyreNotFound:
            return None

    def company():
        if not include_company or not employer_id:
            return None
        from instahyre import companies
        try:
            return P.company_summary(companies.profile(employer_id, with_counts=False))
        except fetch.InstahyreNotFound:
            return None

    outcomes = fetch.run_parallel([page, company], 2)
    ld = outcomes[0][1] if outcomes[0][0] == "ok" else None
    profile = outcomes[1][1] if outcomes[1][0] == "ok" else None
    for status, value in outcomes:
        if status == "error" and not isinstance(value, fetch.InstahyreNotFound):
            print(f"instahyre: job {job} extra fetch skipped: {value}")
    return P.job_details(raw, ld, profile)


def _employer_id_of(raw):
    """The employer id behind a job record: its logo URL carries it
    (/images/profile/base/employer/<id>/…)."""
    import re
    match = re.search(r"/employer/(\d+)/", str(raw.get("employer_profile_url") or ""))
    return int(match.group(1)) if match else None


def batch(jobs, include_company=False):
    """Up to MAX_BATCH jobs by id / link, fetched in parallel. Jobs the site
    does not have are listed under `errors` instead of failing the call."""
    outcomes = fetch.run_parallel([lambda j=j: details(j, include_company) for j in jobs], _workers())
    out, errors = [], {}
    for job_id, (status, value) in zip(jobs, outcomes):
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.InstahyreNotFound):
            errors[str(job_id)] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}


def similar(job):
    """Up to 10 jobs the site lists as similar to `job`."""
    rows = fetch.similar_jobs(job)
    jobs = [P.similar_job(r) for r in rows if isinstance(r, dict)]
    return {"job_id": job, "jobs": jobs, "count": len(jobs)}
