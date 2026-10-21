"""Raw Instahyre payloads -> the API's response shapes. Pure functions over
the site's JSON (fetch.py) and the JSON-LD of its HTML pages; every parser
tolerates a partial record.

Dropped on purpose: `resource_uri` (API-internal), `interview_status` /
`reviewed_at` / `is_strong_match` / `score` (per-candidate fields, always
null for an anonymous client), `candidate_title` (the title plus
"(Internship)" — folded into `is_internship`), `company_name_nopunc`,
`previous_slug`, the search meta's `facet_all_counts` (the total repeated
per facet), `job_experience_levels` (a sitewide histogram, identical for
every query) and `next` / `previous` (rebuilt as this API's pagination)."""
import json
import re
from math import ceil

from instahyre import refdata
from instahyre import shared as S
from instahyre.shared import as_dict, as_list, g


# ---- companies on job cards ----------------------------------------------------------------------------

def employer_card(raw):
    raw = as_dict(raw)
    if not raw:
        return None
    return {
        "id": S.to_int(raw.get("id")),
        "name": S.text(raw.get("company_name")),
        "logo": S.link(raw.get("profile_image_src")),
        "tagline": S.text(raw.get("company_tagline")),
        "about": S.text(raw.get("instahyre_note")),
        "founded_year": S.year(raw.get("company_founded")),
        "employee_count": S.count(raw.get("employee_count")),
        "is_diversity_employer": bool(raw.get("show_diversity_employer_icon")),
        "is_featured_employer": bool(raw.get("show_featured_employer_icon")),
    }


def gender_preference(value):
    return refdata.GENDER_PREFERENCES.get(S.to_int(value))


def _is_internship(raw):
    if isinstance(raw.get("is_internship"), bool):
        return raw["is_internship"]
    candidate = S.text(raw.get("candidate_title")) or ""
    return candidate.lower().endswith("(internship)")


# ---- job cards (search) -------------------------------------------------------------------------------------

def job_card(raw):
    raw = as_dict(raw)
    job_id = S.to_int(raw.get("id"))
    locations = S.split_csv(raw.get("locations"))
    return {
        "id": job_id,
        "title": S.text(raw.get("title")),
        "link": S.link(raw.get("public_url")),
        "is_internship": _is_internship(raw),
        "locations": locations,
        "is_remote": S.is_remote(locations),
        "accepts_other_cities": bool(raw.get("accept_outstation")),
        "gender_preference": gender_preference(raw.get("gender")),
        "skills": S.text_list(raw.get("keywords")),
        "company": employer_card(raw.get("employer")),
    }


def _count_rows(rows, name_key, out_key="name", extra=None):
    out = []
    for row in as_list(rows):
        row = as_dict(row)
        entry = {out_key: row.get(name_key), "count": S.count(row.get("count"))}
        if extra:
            entry = {**extra(row), **entry}
        out.append(entry)
    return out


def facets(meta):
    """The search meta's facet counts, named."""
    meta = as_dict(meta)
    functions = []
    for row in as_list(meta.get("top_job_functions_count")):
        row = as_dict(row)
        functions.append({"id": S.to_int(row.get("id")), "name": S.text(row.get("name")),
                          "type": S.text(row.get("type")) or "job_function", "count": S.count(row.get("count"))})
    industries = []
    for row in as_list(meta.get("top_industry_types_count")):
        row = as_dict(row)
        iid = S.to_int(row.get("name"))
        industries.append({"id": iid, "name": refdata.INDUSTRIES.get(iid) if iid is not None else S.text(row.get("name")),
                           "count": S.count(row.get("count"))})
    sizes = as_dict(meta.get("company_size_count"))
    types = as_dict(meta.get("job_type_counts"))
    # meta.job_experience_levels is NOT a facet of the search: the same
    # sitewide histogram comes back for every query (an empty search too), so
    # it is left out rather than mislabelled.
    return {
        "job_types": {k: S.count(types.get(k)) for k in ("full_time", "internship")} if types else None,
        "company_sizes": {k: S.count(sizes.get(k)) for k in ("small", "medium", "large")} if sizes else None,
        "job_functions": functions,
        "industries": industries,
        "companies": _count_rows(meta.get("top_companies_count"), "name"),
        "locations": _count_rows(meta.get("top_locations_count"), "location"),
    }


def search_result(raw, page):
    raw = as_dict(raw)
    meta = as_dict(raw.get("meta"))
    total = S.count(meta.get("total_count")) or 0
    pages = ceil(total / refdata.PAGE_SIZE) if total else 0
    return {
        "jobs": [job_card(c) for c in as_list(raw.get("objects")) if isinstance(c, dict)],
        "is_count_exact": (meta.get("total_count_relation") or "eq") == "eq",
        "facets": facets(meta),
        "pagination": {"page": page, "items_per_page": refdata.PAGE_SIZE,
                       "total_pages": min(pages, refdata.MAX_PAGE), "total_count": total},
    }


# ---- job details ------------------------------------------------------------------------------------------

_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)


def job_posting_ld(html):
    """The JSON-LD JobPosting of a job page -> {posted_at, employment_type,
    locations: [{city, state, country}], company_website, company_logo};
    None when the page carries none (closed ads)."""
    for block in _LD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "JobPosting":
            continue
        locations = []
        for place in as_list(data.get("jobLocation")):
            address = as_dict(as_dict(place).get("address"))
            city = S.text(address.get("addressLocality")) or S.text(address.get("streetAddress"))
            if city:
                locations.append({"city": city, "state": S.text(address.get("addressRegion")),
                                  "country": S.text(address.get("addressCountry"))})
        org = as_dict(data.get("hiringOrganization"))
        employment = S.text(data.get("employmentType"))
        return {
            "posted_at": S.iso_date(data.get("datePosted")),
            "employment_type": employment.lower() if employment else None,
            "locations": locations,
            "company_website": S.text(org.get("sameAs")),
            "company_logo": S.link(org.get("logo")),
        }
    return None


def job_function_ref(value):
    """A function id / resource uri -> {id, slug, name, category} from the static table."""
    fid = S.id_from_uri(value)
    entry = refdata.JOB_FUNCTIONS.get(fid)
    if not entry:
        return {"id": fid, "slug": None, "name": None, "category": None} if fid is not None else None
    slug, name, cat_id = entry
    cat = refdata.JOB_CATEGORIES.get(cat_id)
    return {"id": fid, "slug": slug, "name": name,
            "category": {"id": cat_id, "name": cat[0] if cat else None} if cat_id is not None else None}


def _functions(raw):
    refs = [job_function_ref(uri) for uri in as_list(raw.get("job_functions"))]
    refs = [r for r in refs if r]
    names = S.text_list(raw.get("job_function_names"))
    if not refs and names:
        by_name = {name.lower(): fid for fid, (_s, name, _c) in refdata.JOB_FUNCTIONS.items()}
        refs = [job_function_ref(by_name.get(n.lower())) or {"id": None, "slug": None, "name": n, "category": None}
                for n in names]
    # the site's names win over the snapshot when both exist (renamed functions)
    for ref, name in zip(refs, names):
        if name and not ref.get("name"):
            ref["name"] = name
    return refs


def internship_terms(raw):
    raw = as_dict(raw)
    if not raw:
        return None
    return {
        "stipend": S.to_int(raw.get("stipend")),
        "currency": refdata.DEFAULT_CURRENCY,
        "period": "monthly",
        "is_paid": bool(raw.get("is_paid")),
        "is_stipend_hidden": bool(raw.get("hide_stipend")),
        "duration_months": S.to_int(raw.get("duration")),
        "start_date": S.iso_date(raw.get("start_date")),
    }


def recruiter(raw):
    name = S.text(raw.get("recruiter_name"))
    if not name and not S.text(raw.get("recruiter_designation")):
        return None
    return {
        "name": name,
        "designation": S.text(raw.get("recruiter_designation")),
        "company_name": S.text(raw.get("recruiter_company_name")),
        "photo": S.link(raw.get("recruiter_profile_url")),
    }


def _job_locations(cities, ld):
    """The record's city list, with each city's state from the page's JSON-LD."""
    states = {loc["city"].lower(): loc.get("state") for loc in as_list((ld or {}).get("locations"))}
    out = []
    for city in cities:
        out.append({"city": city, "state": states.get(city.lower())})
    return out


def job_details(raw, ld=None, company=None):
    """The job record (+ its page's JSON-LD, + the company page) -> the
    /jobs/details shape. `company` is a parsed employer profile or None."""
    raw = as_dict(raw)
    job_id = S.to_int(raw.get("id"))
    if job_id is None:
        return None
    cities = S.text_list(raw.get("locations")) if isinstance(raw.get("locations"), list) else S.split_csv(raw.get("locations"))
    is_internship = _is_internship(raw)
    description_html = S.html_fragment(raw.get("description"))
    minimal_company = {
        "id": g(company, "id") if company else None,
        "name": S.text(raw.get("hiring_company_name")),
        "logo": S.link(raw.get("employer_profile_url")) or (ld or {}).get("company_logo"),
        "website": (ld or {}).get("company_website"),
    }
    if company:
        company = dict(company)
        company.setdefault("website", minimal_company["website"])
    return {
        "id": job_id,
        "title": S.text(raw.get("title")),
        "link": S.link(raw.get("opportunity_url")),
        "is_active": bool(raw.get("is_active")),
        "is_internship": is_internship,
        "employment_type": "internship" if is_internship else "full_time",
        "posted_at": (ld or {}).get("posted_at"),
        "locations": _job_locations(cities, ld),
        "is_remote": S.is_remote(cities),
        "accepts_other_cities": bool(raw.get("accept_outstation")),
        "gender_preference": gender_preference(raw.get("gender")),
        "skills": S.text_list(raw.get("keywords")),
        "experience": {"min_years": S.to_int(raw.get("workex_min")), "max_years": S.to_int(raw.get("workex_max"))},
        "category": S.text(raw.get("job_category")),
        "functions": _functions(raw),
        "description_html": description_html,
        "description_text": S.html_to_text(description_html),
        "internship": internship_terms(raw.get("internship")) if is_internship or raw.get("internship") else None,
        "recruiter": recruiter(raw),
        "company": company or minimal_company,
    }


def merge_card_details(card, detail):
    """A search card + its job record -> the card with the record's extra
    fields (for /jobs/search?include_details=true)."""
    if not detail:
        return dict(card, details=None)
    out = dict(card)
    out["is_active"] = detail.get("is_active")
    out["experience"] = detail.get("experience")
    out["category"] = detail.get("category")
    out["functions"] = detail.get("functions")
    out["description_html"] = detail.get("description_html")
    out["description_text"] = detail.get("description_text")
    out["internship"] = detail.get("internship")
    out["recruiter"] = detail.get("recruiter")
    return out


# ---- employer profiles ------------------------------------------------------------------------------------

def _ratings(raw):
    raw = as_dict(raw)
    if not raw:
        return None
    out = {
        "source": "glassdoor",
        "overall": S.rating(raw.get("overall")),
        "culture_values": S.rating(raw.get("culture_values")),
        "work_life_balance": S.rating(raw.get("work_life_balance")),
        "compensation_benefits": S.rating(raw.get("compensation_benefits")),
        "career_opportunities": S.rating(raw.get("career_opportunities")),
        "diversity_inclusion": S.rating(raw.get("diversity_inclusions")),
        "recommend_to_friend": S.rating(raw.get("recommendation")),
    }
    return out if any(v for k, v in out.items() if k != "source") else None


def _social(raw):
    raw = as_dict(raw)
    keys = ("linkedin", "facebook", "twitter", "instagram", "android_app", "ios_app")
    return {k: S.text(raw.get(k)) for k in keys}


def _headquarters(raw):
    parts = S.text_list(raw) if isinstance(raw, list) else S.split_csv(raw)
    if not parts:
        return None
    return {"city": parts[0], "state": parts[1] if len(parts) > 1 else None}


def _office_photo(raw):
    raw = as_dict(raw)
    title = S.text(raw.get("title"))
    return {"id": S.to_int(raw.get("id")), "title": re.sub(r"\.(webp|jpe?g|png)$", "", title, flags=re.I) if title else None,
            "link": S.link(raw.get("image_url")), "thumbnail_link": S.link(raw.get("thumbnail_url"))}


def employer_job(raw):
    """A job on the company page's own list (first 10 open jobs)."""
    raw = as_dict(raw)
    cities = S.text_list(raw.get("locations")) if isinstance(raw.get("locations"), list) else S.split_csv(raw.get("locations"))
    description_html = S.html_fragment(raw.get("description"))
    return {
        "id": S.to_int(raw.get("id")),
        "title": S.text(raw.get("title")),
        "link": S.link(raw.get("opportunity_url")),
        "is_internship": _is_internship(raw),
        "locations": cities,
        "is_remote": S.is_remote(cities),
        "experience": {"min_years": S.to_int(raw.get("workex_min")), "max_years": S.to_int(raw.get("workex_max"))},
        "description_text": S.html_to_text(description_html),
    }


def _media_item(raw):
    """A press mention on the company page: {id, title, url} -> {id, title, link}."""
    if isinstance(raw, dict):
        out = {"id": S.to_int(raw.get("id")), "title": S.text(raw.get("title")),
               "link": S.link(raw.get("url") or raw.get("link"))}
        return out if out["title"] or out["link"] else None
    text = S.text(raw)
    return {"id": None, "title": None, "link": text} if text else None


def employer_profile(raw, counts=None, employer_id=None):
    """The brand page record -> the /companies/details shape."""
    raw = as_dict(raw)
    eid = S.id_from_uri(raw.get("resource_uri")) or employer_id
    slug = S.text(raw.get("slug"))
    social = as_dict(raw.get("social_accounts"))
    summary_html = S.html_fragment(raw.get("summary"))
    why_us_html = S.html_fragment(raw.get("why_us"))
    interview_html = S.html_fragment(raw.get("interview_process"))
    industries = [{"id": S.to_int(i.get("id")), "name": S.text(i.get("name"))}
                  for i in as_list(raw.get("industry_types")) if isinstance(i, dict)]
    if not industries and S.text(raw.get("industries")):
        industries = [{"id": None, "name": S.text(raw.get("industries"))}]
    out = {
        "id": eid,
        "name": S.text(raw.get("company_name")),
        "slug": slug,
        "link": S.company_link(slug),
        "logo": S.link(raw.get("profile_image_src")),
        "tagline": S.text(raw.get("company_tagline")),
        "about": S.html_to_text(summary_html),
        "about_html": summary_html,
        "why_us": S.html_to_text(why_us_html),
        "why_us_html": why_us_html,
        "interview_process": S.html_to_text(interview_html),
        "interview_process_html": interview_html,
        "founded_year": S.year(raw.get("company_founded")),
        "employee_count": S.count(raw.get("employee_count")),
        "headquarters": _headquarters(raw.get("location")),
        "industries": industries,
        "website": S.text(social.get("website")),
        "social": _social(social),
        "ratings": _ratings(raw.get("glassdoor_data")),
        "benefits": S.text_list(raw.get("benefits")),
        "tech_stack": S.text_list(raw.get("tech_stack")),
        "tech_stack_description": S.text(raw.get("tech_stack_description")),
        "video_link": S.text(raw.get("company_video_link")),
        "office_photos": [_office_photo(p) for p in as_list(raw.get("office_photos")) if isinstance(p, dict)],
        "media_coverage": [m for m in (_media_item(x) for x in as_list(raw.get("media_coverage"))) if m],
        "is_diversity_employer": bool(raw.get("show_diversity_employer_icon")),
        "is_featured_employer": bool(raw.get("show_featured_employer_icon")),
        "jobs_count": S.count(raw.get("jobs_count")),
        "job_counts_by_category": [{"id": S.to_int(c.get("category_id")), "name": S.text(c.get("category_name")),
                                    "count": S.count(c.get("count"))}
                                   for c in as_list(counts) if isinstance(c, dict)] if counts is not None else None,
        "jobs": [employer_job(j) for j in as_list(raw.get("jobs")) if isinstance(j, dict)],
    }
    return out


def company_summary(profile):
    """The company block attached to a job: the profile minus its job list."""
    if not profile:
        return None
    return {k: v for k, v in profile.items() if k not in ("jobs", "job_counts_by_category")}


# ---- similar jobs ----------------------------------------------------------------------------------------

def similar_job(raw):
    raw = as_dict(raw)
    cities = S.split_csv(raw.get("locations"))
    return {
        "id": S.to_int(raw.get("id")),
        "title": S.text(raw.get("title")),
        "link": S.link(raw.get("opportunity_url")),
        "is_internship": _is_internship(raw),
        "locations": cities,
        "is_remote": S.is_remote(cities),
        "company": {"name": S.text(raw.get("hiring_company_name")), "logo": S.link(raw.get("employer_profile_url"))},
    }


# ---- lookups --------------------------------------------------------------------------------------------------

def job_function_entry(raw):
    raw = as_dict(raw)
    cat = as_dict(raw.get("job_category"))
    return {
        "id": S.to_int(raw.get("id")),
        "slug": S.text(raw.get("slug")),
        "name": S.text(raw.get("name")),
        "is_live": bool(raw.get("is_live", True)),
        "category": {"id": S.to_int(cat.get("id")), "name": S.text(cat.get("name")), "is_tech": bool(cat.get("is_tech"))}
        if cat else None,
    }


def industry_entry(raw):
    raw = as_dict(raw)
    return {"id": S.to_int(raw.get("id")), "name": S.text(raw.get("name"))}


def location_entry(raw):
    raw = as_dict(raw)
    value = S.text(raw.get("value")) or S.text(raw.get("name"))
    alternates = raw.get("alter") or []
    if isinstance(alternates, str):
        alternates = [a.strip() for a in alternates.split(",") if a.strip()]
    return {
        "value": value,
        "name": S.text(raw.get("name")) or value,
        "group": S.text(raw.get("type")),
        "alternate_names": S.text_list(alternates),
        "country_code": S.text(raw.get("iso_alpha_code")) or None,
    }


def location_table(data):
    """The picker lists -> one deduped list keyed on the filter value, the
    remote entry first, then regions, metros and the states in site order."""
    data = as_dict(data)
    seen = {}
    for raw in as_list(data.get("cities_preferred")) + as_list(data.get("cities_current")):
        entry = location_entry(raw)
        if entry["value"] and entry["value"] not in seen:
            seen[entry["value"]] = entry
    rank = {"remote": 0, "regions": 1, "top metropolitan cities": 2}
    order = list(seen.values())
    return sorted(order, key=lambda e: (rank.get(e["group"], 3), 0 if rank.get(e["group"]) is not None else order.index(e)))


def company_suggestion(raw):
    raw = as_dict(raw)
    return {"id": S.to_int(raw.get("id")), "name": S.text(raw.get("company_name")),
            "alternate_names": [a for a in S.text_list((raw.get("alternate_names_nopunc") or "").split(","))
                                if a != (raw.get("company_name_nopunc") or "")]}


def skill_suggestion(raw):
    raw = as_dict(raw)
    return {"id": S.to_int(raw.get("id")), "name": S.text(raw.get("name")), "slug": S.text(raw.get("slug")),
            "alternate_names": S.text_list((raw.get("alternate_names") or "").split(","))}
