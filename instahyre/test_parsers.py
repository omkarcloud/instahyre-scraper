"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (instahyre/fixtures/*.gz, raw payloads captured 2026-10-19 from
www.instahyre.com) — no network.

    python -m pytest instahyre/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from instahyre import companies, fetch, jobs, lookups, parsers as P, refdata, refs, schemas, shared as S  # noqa: E402
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def fx_html(name):
    with gzip.open(os.path.join(FX, name + ".html.gz"), "rt", encoding="utf-8") as f:
        return f.read()


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "446555", "https://www.instahyre.com/job-446555-software-engineer-discovery-at-axiamatic-2-bangalore/",
    "www.instahyre.com/job-446555-x/", "job-446555-software-engineer", "https://instahyre.com/job-446555/",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == 446555


@pytest.mark.parametrize("value", ["", "abc", "https://www.instahyre.com/search-jobs/", "https://example.com/job-1-x/"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


def test_resolve_jobs():
    assert refs.resolve_jobs("446555, https://www.instahyre.com/job-440752-llm-developer-at-accenture-2-bangalore/, 446555") == [446555, 440752]
    with pytest.raises(ValueError):
        refs.resolve_jobs(", ,")
    with pytest.raises(ValueError):
        refs.resolve_jobs(",".join(str(i) for i in range(1, refdata.MAX_BATCH + 2)))


@pytest.mark.parametrize("value,expected", [
    ("35927", {"id": 35927, "slug": None, "name": None}),
    ("https://www.instahyre.com/jobs-at-axiamatic-2/", {"id": None, "slug": "axiamatic-2", "name": None}),
    ("jobs-at-Axiamatic-2", {"id": None, "slug": "axiamatic-2", "name": None}),
    ("Deutsche Telekom Digital Labs", {"id": None, "slug": None, "name": "Deutsche Telekom Digital Labs"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://www.instahyre.com/search-jobs/", "https://example.com/jobs-at-x/", "a/b"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


def test_resolve_locations():
    assert refs.resolve_locations("bengaluru, Remote, delhi ncr, Pune, pune") == ["Bangalore", "Work From Home", "Delhi / NCR", "Pune"]
    assert refs.resolve_locations("south india") == ["South India"]
    assert refs.resolve_locations("") is None
    with pytest.raises(ValueError):
        refs.resolve_locations("Atlantis")


def test_resolve_taxonomies():
    assert refs.resolve_job_functions("backend-development, 1, Data Science / Machine Learning") == [10, 1, 9]
    assert refs.resolve_job_categories("software-engineering, Sales") == [1, refs.resolve_job_categories("sales")[0]]
    assert refs.resolve_industries("13, banking / financial services") == [13, 9]
    with pytest.raises(ValueError):
        refs.resolve_job_functions("devops")      # the real slug is devops-cloud
    assert refs.resolve_company_names("Amazon, Accenture, Amazon") == ["Amazon", "Accenture"]


# ---- schemas ---------------------------------------------------------------------------------

def test_search_schema():
    data, err = load_query(schemas.JobSearchSchema, {
        "query": " python ", "location": "bangalore,remote", "experience_years": "3", "job_type": "Internship",
        "company_size": "LARGE", "job_function": "backend-development", "job_category": "1", "industry": "Retail",
        "company": "Amazon", "page": "2", "include_details": "yes"})
    assert err is None
    assert data == {"query": "python", "location": ["Bangalore", "Work From Home"], "experience_years": 3,
                    "job_type": "internship", "company_size": "large", "job_function": [10], "job_category": [1],
                    "industry": [refs.resolve_industries("Retail")[0]], "company": ["Amazon"], "page": 2,
                    "include_details": True}
    data, err = load_query(schemas.JobSearchSchema, {})
    assert err is None and data["page"] == 1 and data["include_details"] is False and data["location"] is None
    assert load_query(schemas.JobSearchSchema, {"page": str(refdata.MAX_PAGE + 1)})[1]
    assert load_query(schemas.JobSearchSchema, {"job_type": "contract"})[1]
    assert load_query(schemas.JobSearchSchema, {"experience_years": "-1"})[1]
    assert load_query(schemas.JobSearchSchema, {"url": "x"})[1]          # unknown params are rejected


def test_other_schemas():
    assert load_query(schemas.JobSchema, {"job": "https://www.instahyre.com/job-446555-x-bangalore/"})[0] == {"job": 446555, "include_company": True}
    assert load_query(schemas.JobBatchSchema, {"jobs": "1,2"})[0] == {"jobs": [1, 2], "include_company": False}
    assert load_query(schemas.CompanySchema, {"company": "Accenture", "include_jobs": "0"})[0] == {
        "company": {"id": None, "slug": None, "name": "Accenture"}, "include_jobs": False}
    data, err = load_query(schemas.CompanyJobsSchema, {"company": "2070", "job_type": "full_time", "location": "Pune"})
    assert err is None and data["company"]["id"] == 2070 and data["location"] == ["Pune"] and data["page"] == 1
    assert load_query(schemas.AutocompleteSchema, {"query": "py"})[0] == {"query": "py", "type": "skills", "limit": 10}
    assert load_query(schemas.AutocompleteSchema, {"query": "py", "type": "cities"})[1]
    assert load_query(schemas.CompanySearchSchema, {"query": ""})[1]
    assert load_query(schemas.EmptySchema, {"page": "1"})[1]


# ---- shared helpers ------------------------------------------------------------------------------

def test_shared_helpers():
    assert S.split_csv("Bangalore,Gurgaon, Hyderabad") == ["Bangalore", "Gurgaon", "Hyderabad"]
    assert S.is_remote(["Work From Home"]) and not S.is_remote(["Pune"])
    assert S.year(2021) == 2021 and S.year(0) is None and S.year("abc") is None
    assert S.id_from_uri("/api/v1/job_function/10") == 10 and S.id_from_uri(None) is None
    assert S.job_id_from_link("https://www.instahyre.com/job-446555-x-bangalore/") == 446555
    assert S.html_fragment("<html><body><p>Hi</p></body></html>") == "<p>Hi</p>"
    assert S.html_to_text("<p>A</p><ul><li>one</li><li>two</li></ul>") == "A\n- one\n- two"
    assert S.iso_date("2026-10-12") == "2026-10-12" and S.iso_date(None) is None
    assert S.company_link("axiamatic-2") == "https://www.instahyre.com/jobs-at-axiamatic-2/"


# ---- parsers -----------------------------------------------------------------------------------

def test_search_result():
    out = P.search_result(fx("search_python_bangalore"), 1)
    assert len(out["jobs"]) == refdata.PAGE_SIZE and out["pagination"]["total_count"] > 1000
    assert out["pagination"]["items_per_page"] == 35 and out["pagination"]["total_pages"] <= refdata.MAX_PAGE
    assert out["is_count_exact"] is True
    card = out["jobs"][0]
    assert card["id"] and card["title"] and card["link"].startswith("https://www.instahyre.com/job-")
    assert "Bangalore" in card["locations"] and card["skills"] and card["company"]["id"] and card["company"]["name"]
    assert card["gender_preference"] is None and isinstance(card["accepts_other_cities"], bool)
    assert set(card) == {"id", "title", "link", "is_internship", "locations", "is_remote", "accepts_other_cities",
                         "gender_preference", "skills", "company"}
    facets = out["facets"]
    assert facets["job_types"]["full_time"] > 0 and facets["company_sizes"]["large"] > 0
    assert facets["job_functions"][0]["name"] and facets["industries"][0]["name"] == "Computer Software / IT / Internet"
    assert facets["companies"][0]["count"] and facets["locations"][0]["name"] == "Bangalore"
    assert "experience_levels" not in facets
    internships = P.search_result(fx("search_internships"), 1)
    assert all(j["is_internship"] for j in internships["jobs"])
    empty = P.search_result(fx("search_empty"), 1)
    assert empty["jobs"] == [] and empty["pagination"]["total_pages"] == 0 and empty["pagination"]["total_count"] == 0
    p2 = P.search_result(fx("search_accenture_backend_p2"), 2)
    assert p2["pagination"]["page"] == 2 and all(j["company"]["name"] == "Accenture" for j in p2["jobs"])


def test_job_posting_ld():
    ld = P.job_posting_ld(fx_html("job_page"))
    assert ld["posted_at"] and ld["employment_type"] == "full_time" and ld["locations"][0]["state"] == "Karnataka"
    assert ld["company_website"].startswith("http")
    assert P.job_posting_ld(fx_html("job_page_closed")) is None
    assert P.job_posting_ld("") is None


def test_job_details():
    raw = fx("job_detail")
    ld = P.job_posting_ld(fx_html("job_page"))
    company = P.company_summary(P.employer_profile(fx("employer"), employer_id=raw and 5003))
    out = P.job_details(raw, ld, company)
    assert out["id"] == raw["id"] and out["is_active"] is True and out["employment_type"] == "full_time"
    assert out["posted_at"] == ld["posted_at"] and out["locations"] == [{"city": "Bangalore", "state": "Karnataka"}]
    assert out["experience"]["min_years"] is not None and out["category"] and out["functions"][0]["slug"]
    assert out["description_html"].startswith("<") and "<html>" not in out["description_html"]
    assert out["description_text"] and out["recruiter"]["name"] and out["internship"] is None
    assert out["company"]["name"] and "jobs" not in out["company"] and out["company"]["website"]
    bare = P.job_details(raw)
    assert bare["posted_at"] is None and bare["locations"] == [{"city": "Bangalore", "state": None}]
    assert bare["company"] == {"id": None, "name": raw["hiring_company_name"], "logo": raw["employer_profile_url"], "website": None}
    intern = P.job_details(fx("job_detail_internship"))
    assert intern["is_internship"] and intern["employment_type"] == "internship"
    assert intern["internship"] == {"stipend": 40000, "currency": "INR", "period": "monthly", "is_paid": True,
                                    "is_stipend_hidden": False, "duration_months": 6, "start_date": "2026-11-02"}
    closed = P.job_details(fx("job_detail_closed"))
    assert closed["is_active"] is False and closed["posted_at"] is None
    assert P.job_details({}) is None and P.job_details(None) is None


def test_merge_card_details():
    card = P.job_card(fx("search_python_bangalore")["objects"][0])
    merged = P.merge_card_details(card, P.job_details(fx("job_detail")))
    assert merged["description_text"] and merged["experience"] and merged["id"] == card["id"]
    assert P.merge_card_details(card, None)["details"] is None


def test_employer_profile():
    out = P.employer_profile(fx("employer_accenture"), fx("employer_job_counts"), employer_id=2070)
    assert out["id"] == 2070 and out["name"] == "Accenture" and out["slug"] == "accenture-2"
    assert out["link"] == "https://www.instahyre.com/jobs-at-accenture-2/" and out["logo"]
    assert out["ratings"]["source"] == "glassdoor" and 0 < out["ratings"]["overall"] <= 5 and out["ratings"]["recommend_to_friend"]
    assert out["tech_stack"] and out["industries"][0]["name"] and out["headquarters"]["city"]
    assert out["jobs_count"] > 100 and len(out["jobs"]) == 10 and out["jobs"][0]["link"] and out["jobs"][0]["experience"]
    assert out["job_counts_by_category"][0]["name"] and out["about"] and out["about_html"].startswith("<")
    assert set(out["social"]) == {"linkedin", "facebook", "twitter", "instagram", "android_app", "ios_app"}
    small = P.employer_profile(fx("employer"))          # Nineleaps: rated, no benefits listed
    assert small["name"] == "Nineleaps" and small["ratings"]["overall"] and small["benefits"] == []
    assert small["website"] and small["office_photos"][0]["link"]
    assert small["founded_year"] and small["employee_count"] and small["job_counts_by_category"] is None
    assert P.company_summary(small) and "jobs" not in P.company_summary(small)
    assert P.employer_profile({})["name"] is None


def test_media_coverage_items():
    raw = {"company_name": "Uber", "media_coverage": [
        {"resource_uri": "/api/v1/brand_page/media/653", "id": 653, "title": "Uber to open 150,000 sq ft office in Hyderabad",
         "url": "http://www.businessinsider.in/x.cms"}, {"id": 1, "title": "", "url": ""}, "http://example.com/a"]}
    assert P.employer_profile(raw)["media_coverage"] == [
        {"id": 653, "title": "Uber to open 150,000 sq ft office in Hyderabad", "link": "http://www.businessinsider.in/x.cms"},
        {"id": None, "title": None, "link": "http://example.com/a"}]


def test_similar_and_lookups():
    sim = [P.similar_job(r) for r in fx("similar_jobs")]
    assert len(sim) == 10 and sim[0]["link"] and sim[0]["company"]["name"]
    fns = [P.job_function_entry(r) for r in fx("job_functions")]
    assert len(fns) == 107 and fns[0]["slug"] and fns[0]["category"]["name"]
    inds = [P.industry_entry(r) for r in fx("industry_types")]
    assert len(inds) == 74 and {"id": 13, "name": "Computer Software / IT / Internet"} in inds
    locs = P.location_table(fx("location_data"))
    values = [l["value"] for l in locs]
    assert locs[0]["value"] == "Work From Home" and "Bangalore" in values and "South India" in values
    assert len(values) == len(set(values)) and next(l for l in locs if l["value"] == "Bangalore")["alternate_names"] == ["Bengaluru", "Bangaluru"]
    assert P.company_suggestion(fx("suggest_companies")[0]) == {"id": 34545, "name": "Amazatic", "alternate_names": []}
    skill = P.skill_suggestion(fx("suggest_skills")[0])
    assert skill["name"] == "Python" and skill["slug"] == "python" and "Python3" in skill["alternate_names"]
    assert P.location_entry(fx("suggest_locations")[0])["value"]


# ---- endpoint functions over the fixtures (transport monkeypatched) --------------------------------

@pytest.fixture
def offline(monkeypatch):
    calls = []

    def job_search(params, label=None):
        calls.append(("search", dict(params)))
        if params.get("job_type") == 2:
            return fx("search_internships")
        if params.get("companies"):
            return fx("search_accenture_backend_p2")
        if params.get("skills") == "zzqqxx":
            return fx("search_empty")
        return fx("search_python_bangalore")

    def job_detail(job_id):
        calls.append(("detail", job_id))
        if job_id == 99999999:
            raise fetch.InstahyreNotFound("no")
        if job_id == 300000:
            return fx("job_detail_closed")
        if job_id == 445808:
            return fx("job_detail_internship")
        return fx("job_detail")

    monkeypatch.setattr(fetch, "job_search", job_search)
    monkeypatch.setattr(fetch, "job_detail", job_detail)
    monkeypatch.setattr(fetch, "job_page", lambda path, label=None: fx_html("job_page_closed" if "300000" in path else "job_page"))
    monkeypatch.setattr(fetch, "employer", lambda eid: fx("employer_accenture") if eid == 2070 else fx("employer"))
    monkeypatch.setattr(fetch, "employer_job_counts", lambda eid: fx("employer_job_counts"))
    monkeypatch.setattr(fetch, "similar_jobs", lambda jid: fx("similar_jobs"))
    monkeypatch.setattr(fetch, "job_functions", lambda: fx("job_functions"))
    monkeypatch.setattr(fetch, "industry_types", lambda: fx("industry_types"))
    monkeypatch.setattr(fetch, "location_data", lambda: fx("location_data"))
    monkeypatch.setattr(fetch, "autocomplete_companies", lambda q: fx("suggest_companies") if q.lower().startswith("amaz") else [])
    monkeypatch.setattr(fetch, "autocomplete_skills", lambda q: fx("suggest_skills"))
    monkeypatch.setattr(fetch, "autocomplete_locations", lambda q: fx("suggest_locations"))
    monkeypatch.setattr(fetch, "company_page_employer_id", lambda slug: 35927 if slug == "axiamatic-2" else (_ for _ in ()).throw(fetch.InstahyreNotFound("no")))
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    return calls


def test_jobs_search_offline(offline):
    out = jobs.search(query="python", location=["Bangalore"], page=3, job_function=[10], industry=[13], company_size="large")
    sent = offline[0][1]
    assert sent["skills"] == "python" and sent["jobLocations"] == ["Bangalore"] and sent["offset"] == 70
    assert sent["job_functions"] == [10] and sent["industry_types"] == [13] and sent["company_size"] == 2
    assert out["filters"]["job_functions"][0]["slug"] == "backend-development" and out["filters"]["industries"][0]["name"]
    assert out["pagination"]["page"] == 3 and len(out["jobs"]) == 35
    with pytest.raises(ValueError):
        jobs.search(page=refdata.MAX_PAGE + 1)
    detailed = jobs.search(job_type="internship", include_details=True)
    assert detailed["jobs"][0]["description_text"] and detailed["jobs"][0]["internship"]["stipend"] == 40000
    stats = jobs.stats(query="zzqqxx")
    assert stats["total_count"] == 0 and stats["facets"]["companies"] == [] and stats["filters"]["query"] == "zzqqxx"


def test_jobs_details_offline(offline):
    out = jobs.details(439850)
    assert out["posted_at"] and out["company"]["id"] == 5003 and out["company"]["ratings"] and "jobs" not in out["company"]
    bare = jobs.details(439850, include_company=False)
    assert bare["company"]["id"] is None and bare["posted_at"]
    closed = jobs.details(300000, include_company=False)
    assert closed["is_active"] is False and closed["posted_at"] is None
    with pytest.raises(fetch.InstahyreNotFound):
        jobs.details(99999999)
    batch = jobs.batch([439850, 99999999])
    assert batch["count"] == 1 and batch["errors"] == {"99999999": "not found"}
    sim = jobs.similar(439850)
    assert sim["count"] == 10 and sim["job_id"] == 439850


def test_companies_offline(offline):
    out = companies.details({"id": 2070, "slug": None, "name": None})
    assert out["name"] == "Accenture" and out["job_counts_by_category"] and len(out["jobs"]) == 10
    out = companies.details({"id": None, "slug": "axiamatic-2", "name": None}, include_jobs=False)
    assert out["name"] == "Nineleaps" and out["jobs"] is None      # the fixture served for every id but 2070
    assert companies.resolve_id({"id": None, "slug": None, "name": "amazatic"}) == 34545
    with pytest.raises(fetch.InstahyreNotFound):
        companies.resolve_id({"id": None, "slug": None, "name": "nobody"})
    with pytest.raises(fetch.InstahyreNotFound):
        companies.details({"id": None, "slug": "nope", "name": None})
    listing = companies.open_jobs({"id": 2070, "slug": None, "name": None}, page=2, job_type="full_time")
    assert listing["company"]["name"] == "Accenture" and listing["pagination"]["page"] == 2
    assert [c for c in offline if c[0] == "search"][-1][1]["companies"] == ["Accenture"]
    assert companies.search("amaz", 2)["count"] == 2


def test_lookups_offline(offline):
    fns = lookups.job_functions()
    assert fns["count"] == 107 and fns["source"] == "site" and len(fns["job_categories"]) == 19
    assert fns["job_categories"][0]["functions"]
    assert lookups.industries()["count"] == 74
    locs = lookups.locations()
    assert locs["count"] > 250 and locs["locations"][0]["value"] == "Work From Home" and "regions" in locs["groups"]
    assert lookups.autocomplete("pyth")["suggestions"][0]["name"] == "Python"
    assert lookups.autocomplete("amaz", "companies", 1)["count"] == 1
    assert lookups.autocomplete("pun", "locations")["suggestions"][0]["value"]


def test_lookups_static_fallback(monkeypatch):
    def boom():
        raise fetch.InstahyreUpstreamError("down")
    monkeypatch.setattr(fetch, "job_functions", boom)
    monkeypatch.setattr(fetch, "industry_types", boom)
    monkeypatch.setattr(fetch, "location_data", boom)
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    assert lookups.job_functions()["source"] == "static" and lookups.job_functions()["count"] == 107
    assert lookups.industries()["source"] == "static" and lookups.industries()["count"] == 74
    locs = lookups.locations()
    assert locs["source"] == "static" and locs["count"] > 250


# ---- egress: proxy only ----------------------------------------------------------------------------

def test_proxy_only_egress(monkeypatch):
    import config
    monkeypatch.setattr(config, "instahyre_proxy", lambda fallback=False: None)
    monkeypatch.delattr(config, "INSTAHYRE_ALLOW_DIRECT", raising=False)
    with pytest.raises(fetch.InstahyreUpstreamError, match="never contacted"):
        fetch._proxy()
    monkeypatch.setattr(config, "INSTAHYRE_ALLOW_DIRECT", True, raising=False)
    assert fetch._proxy() is None                       # the open-source kit's opt-in
    monkeypatch.setattr(config, "instahyre_proxy", lambda fallback=False: "http://user:pass@gw:1")
    assert fetch._proxy(fallback=True) == "http://user:pass@gw:1"


def test_service_config_has_no_direct_mode():
    import config
    if getattr(config, "INSTAHYRE_ALLOW_DIRECT", False):
        pytest.skip("open-source kit: direct mode is its own opt-in")
    assert config.INSTAHYRE_PROXY_COUNTRY and not getattr(config, "INSTAHYRE_ALLOW_DIRECT", False)
    assert config.instahyre_proxy() and config.instahyre_proxy(fallback=True)
