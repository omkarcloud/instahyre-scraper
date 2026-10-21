"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from instahyre.companies import details as company_details
from instahyre.jobs import details as job_details
from instahyre.jobs import search as search_jobs
from instahyre.refs import resolve_company, resolve_job, resolve_locations

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id or any instahyre.com job link
    save("job_446940.json", job_details(resolve_job(
        "https://www.instahyre.com/job-446940-senior-software-engineer-l5-at-google-2-hyderabad/")))

    # 35 jobs per page, with facet counts; locations as Instahyre lists them
    save("search_python_bangalore.json", search_jobs(query="python", location=resolve_locations("Bangalore")))

    # a company name, id, or /jobs-at-<slug>/ link
    save("company_google.json", company_details(resolve_company("Google")))
