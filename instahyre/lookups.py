"""/instahyre/job-functions, /instahyre/industries, /instahyre/locations,
/instahyre/autocomplete — the three lookup lists behind the search filters
(live from the site, the static snapshot in refdata when it does not
answer) and the search box's suggestions (locations, companies, skills)."""
from instahyre import cache_config as ttl
from instahyre import fetch, refdata
from instahyre import parsers as P


def _live(name, build):
    try:
        return fetch.shared_raw(name, {}, build, ttl.LOOKUP_RAW_CACHE), "site"
    except (fetch.InstahyreUpstreamError, fetch.InstahyreNotFound, fetch.InstahyreBadRequest) as e:
        print(f"instahyre: live {name} skipped: {e}")
        return None, "static"


def job_functions():
    """The 107 job functions (the `job_function` filter's slugs / ids) with
    their 19 categories (the `job_category` filter)."""
    rows, source = _live("job_functions", fetch.job_functions)
    functions = [P.job_function_entry(r) for r in (rows or []) if isinstance(r, dict)]
    if len(functions) < 50:
        functions = [{"id": fid, "slug": slug, "name": name, "is_live": True,
                      "category": {"id": cid, "name": refdata.JOB_CATEGORIES.get(cid, (None, None))[0],
                                   "is_tech": refdata.JOB_CATEGORIES.get(cid, (None, False))[1]}}
                     for fid, (slug, name, cid) in sorted(refdata.JOB_FUNCTIONS.items(), key=lambda kv: kv[1][1])]
        source = "static"
    categories = {}
    for f in functions:
        cat = f.get("category") or {}
        if cat.get("id") is not None and cat["id"] not in categories:
            categories[cat["id"]] = {"id": cat["id"], "name": cat.get("name"), "is_tech": cat.get("is_tech"),
                                     "functions": []}
        if cat.get("id") is not None:
            categories[cat["id"]]["functions"].append({"id": f["id"], "slug": f["slug"], "name": f["name"]})
    return {"source": source, "job_functions": functions, "count": len(functions),
            "job_categories": sorted(categories.values(), key=lambda c: c["name"] or "")}


def industries():
    """The 74 industry types (the `industry` filter's ids / names)."""
    rows, source = _live("industry_types", fetch.industry_types)
    out = [P.industry_entry(r) for r in (rows or []) if isinstance(r, dict)]
    if len(out) < 30:
        out = [{"id": iid, "name": name} for iid, name in sorted(refdata.INDUSTRIES.items(), key=lambda kv: kv[1])]
        source = "static"
    return {"source": source, "industries": out, "count": len(out)}


def locations():
    """The location picker: the `location` filter's values (remote, the
    regions, the metros, every city by state) with their alternate names."""
    data, source = _live("locations", fetch.location_data)
    out = P.location_table(data) if data else []
    if len(out) < 100:
        out = [{"value": value, "name": name, "group": group, "alternate_names": list(alternates), "country_code": None}
               for value, (name, group, alternates) in refdata.LOCATIONS.items()]
        source = "static"
    groups = []
    for entry in out:
        if entry["group"] and entry["group"] not in groups:
            groups.append(entry["group"])
    return {"source": source, "locations": out, "count": len(out), "groups": groups}


def autocomplete(query, type="skills", limit=10):
    """The search box's suggestions: skills (with their alternate
    spellings), companies (with the id /companies/* takes) or locations."""
    if type == "companies":
        rows = fetch.autocomplete_companies(query)
        items = [P.company_suggestion(r) for r in rows if isinstance(r, dict)]
    elif type == "locations":
        rows = fetch.autocomplete_locations(query)
        items = [P.location_entry(r) for r in rows if isinstance(r, dict)]
    else:
        rows = fetch.autocomplete_skills(query)
        items = [P.skill_suggestion(r) for r in rows if isinstance(r, dict)]
    items = items[:limit]
    return {"query": query, "type": type, "suggestions": items, "count": len(items)}
