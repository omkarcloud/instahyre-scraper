"""Live endpoint smoke tests: one call per /instahyre/* route against a
running service, with example values proven to return data (2026-10-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless INSTAHYRE_BASE points at a running service:

    SCRAPERS_PORT=6091 ONLY_SCRAPER=instahyre python run.py
    INSTAHYRE_BASE=http://127.0.0.1:6091 python -m pytest instahyre/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("INSTAHYRE_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set INSTAHYRE_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/instahyre/jobs/search", query="python", location="Bangalore")
    assert body["count"] > 500 and body["per_page"] == 35 and len(body["jobs"]) == 35 and body["next"]
    job = body["jobs"][0]
    assert job["id"] and job["title"] and job["link"].startswith("https://www.instahyre.com/job-")
    assert job["skills"] and job["company"]["name"] and body["facets"]["job_functions"]
    assert body["filters"]["locations"] == ["Bangalore"]
    page2 = call("/instahyre/jobs/search", query="python", location="Bangalore", page=2)
    assert page2["current_page"] == 2 and page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/instahyre/jobs/search", job_type="internship", location="remote,bengaluru", include_details="true")
    assert body["jobs"] and all(j["is_internship"] for j in body["jobs"])
    assert any(j.get("internship") for j in body["jobs"]) and body["jobs"][0]["description_text"]
    body = call("/instahyre/jobs/search", job_function="backend-development,devops-cloud", company_size="small",
                experience_years=0, industry="Computer Software / IT / Internet")
    assert body["jobs"] and body["filters"]["job_functions"][0]["name"] == "Backend Development"
    body = call("/instahyre/jobs/search", company="Accenture,Amazon")
    assert body["jobs"] and {j["company"]["name"] for j in body["jobs"]} <= {"Accenture", "Amazon"}
    assert status("/instahyre/jobs/search", location="Atlantis") == 400
    assert status("/instahyre/jobs/search", page=286) == 400


def test_job_stats():
    body = call("/instahyre/jobs/stats", job_category="Data Science & Analytics", company_size="large")
    assert body["total_count"] > 100 and body["facets"]["company_sizes"]["large"] > 100
    assert body["facets"]["locations"][0]["count"] and body["filters"]["job_categories"][0]["name"] == "Data Science & Analytics"
    assert "jobs" not in body


def test_job_details():
    body = call("/instahyre/jobs/details", job="https://www.instahyre.com/job-446940-senior-software-engineer-l5-at-google-2-hyderabad/")
    assert body["id"] == 446940 and body["description_html"] and body["description_text"] and body["posted_at"]
    assert body["experience"]["max_years"] is not None and body["functions"][0]["slug"] and body["recruiter"]["name"]
    assert body["locations"][0]["state"] and body["company"]["id"] == 5186 and body["company"]["ratings"]["overall"]
    assert body["company"]["link"].startswith("https://www.instahyre.com/jobs-at-")
    listing = call("/instahyre/jobs/search", query="python", location="Bangalore")
    job = listing["jobs"][0]
    assert bare["company"]["id"] is None and bare["company"]["name"] == job["company"]["name"]
    closed = call("/instahyre/jobs/details", job=300000, include_company="false")
    assert closed["is_active"] is False and closed["posted_at"] is None
    assert status("/instahyre/jobs/details", job=99999999) == 404
    assert status("/instahyre/jobs/details", job="abc") == 400


def test_job_batch_and_similar():
    body = call("/instahyre/jobs/batch", jobs="446940,443858")
    assert body["count"] == 2 and body["errors"] is None and {j["company"]["name"] for j in body["jobs"]} == {"Google", "Uber"}
    body = call("/instahyre/jobs/similar", job="446940")
    assert body["job_id"] == 446940 and body["count"] > 0 and body["jobs"][0]["link"]
    listing = call("/instahyre/jobs/search", query="react", location="Pune")
    ids = [j["id"] for j in listing["jobs"][:3]]
    body = call("/instahyre/jobs/batch", jobs=",".join(str(i) for i in ids + [99999999]))
    assert body["count"] == 3 and body["errors"] == {"99999999": "not found"}


def test_company_details():
    body = call("/instahyre/companies/details", company="Google")
    assert body["id"] == 5186 and body["slug"] == "google-2" and body["ratings"]["overall"] and body["benefits"]
    body = call("/instahyre/companies/details", company="Accenture")
    assert body["id"] == 2070 and body["slug"] == "accenture-2" and body["ratings"]["overall"] and body["tech_stack"]
    assert body["jobs_count"] > 50 and len(body["jobs"]) == 10 and body["job_counts_by_category"][0]["count"]
    assert body["social"]["linkedin"] or body["website"]
    body = call("/instahyre/companies/details", company="https://www.instahyre.com/jobs-at-axiamatic-2/", include_jobs="false")
    assert body["id"] == 35927 and body["name"] == "Axiamatic" and body["jobs"] is None and body["benefits"]
    assert status("/instahyre/companies/details", company="zzqqxx nonexistent corp") == 404
    assert status("/instahyre/companies/details", company="jobs-at-zzqqxx-nonexistent") == 404


def test_company_jobs_and_search():
    body = call("/instahyre/companies/jobs", company="Google")
    assert body["count"] > 5 and body["jobs"] and all(j["company"]["name"] == "Google" for j in body["jobs"])
    assert body["company"]["slug"] == "google-2"
    body = call("/instahyre/companies/jobs", company=2070, job_type="full_time")
    assert body["count"] > 50 and body["jobs"] and all(j["company"]["name"] == "Accenture" for j in body["jobs"])
    assert body["company"]["slug"] == "accenture-2" and body["next"]
    body = call("/instahyre/companies/search", query="google")
    assert body["companies"][0] == {"id": 5186, "name": "Google", "alternate_names": body["companies"][0]["alternate_names"]}
    body = call("/instahyre/companies/search", query="amaz", limit=5)
    assert body["count"] > 0 and body["companies"][0]["id"] and body["companies"][0]["name"]


def test_lookups():
    body = call("/instahyre/job-functions")
    assert body["count"] == 107 and len(body["job_categories"]) == 19 and body["job_functions"][0]["slug"]
    body = call("/instahyre/industries")
    assert body["count"] == 74
    body = call("/instahyre/locations")
    assert body["count"] > 250 and body["locations"][0]["value"] == "Work From Home"
    body = call("/instahyre/autocomplete", query="python")
    assert body["suggestions"][0]["name"] == "Python"
    body = call("/instahyre/autocomplete", query="amaz", type="companies", limit=3)
    assert body["count"] == 3 and body["suggestions"][0]["id"]
    body = call("/instahyre/autocomplete", query="pun", type="locations")
    assert body["suggestions"][0]["value"]
    assert status("/instahyre/autocomplete", query="x", type="cities") == 400
