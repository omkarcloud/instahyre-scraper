# 💼 Instahyre Scraper

Instahyre Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Instahyre job and company data for free.

## ✨ What Can I Get?

- 💼 **12,000+ live tech jobs** — full description, skills, experience band, recruiter & posting date
- 🏢 **30,000+ hiring companies** — Glassdoor ratings, benefits, tech stack, headquarters & open jobs
- 🔍 **Search with every Instahyre filter** — skill, city, experience, job type, company size, 107 functions & 74 industries
- 📊 **Hiring-market stats in one call** — job counts by company size, function, industry, top companies & cities

## 🎥 Example: A Full Instahyre Job

```json
{
  "id": 446940,
  "title": "Senior Software Engineer (L5)",
  "link": "https://www.instahyre.com/job-446940-senior-software-engineer-l5-at-google-2-hyderabad/",
  "is_active": true,
  "employment_type": "full_time",
  "posted_at": "2026-10-14",
  "locations": [{ "city": "Hyderabad", "state": "Telangana" }],
  "skills": ["LLM", "full stack", "go", "large language models"],
  "experience": { "min_years": 8, "max_years": 12 },
  "category": "Data Science & Analytics",
  "functions": [
    { "id": 9, "slug": "data-science-machine-learning", "name": "Data Science / Machine Learning" }
  ],
  "description_text": "The Apigee India team is looking for a Senior Software Developer (L5) to join us in building and scaling the next generation of API management and AI integration tools ...",
  "recruiter": { "name": "Pradeep Kumar Kannekanti", "designation": "Recruiting Specialist", "company_name": "Google" },
  "company": {
    "id": 5186,
    "name": "Google",
    "link": "https://www.instahyre.com/jobs-at-google-2/",
    "tagline": "Do the Right Thing",
    "founded_year": 1998,
    "website": "http://www.google.com/",
    "ratings": { "source": "glassdoor", "overall": 4.4, "work_life_balance": 4.2, "compensation_benefits": 3.7, "career_opportunities": 4.1 },
    "benefits": ["Health insurance", "Free meals", "Gym in office"],
    "jobs_count": 30
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Instahyre Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/instahyre-scraper
cd instahyre-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=446940"
```

```json
{
  "id": 446940,
  "title": "Senior Software Engineer (L5)",
  "link": "https://www.instahyre.com/job-446940-senior-software-engineer-l5-at-google-2-hyderabad/",
  "is_active": true,
  "posted_at": "2026-10-14",
  "locations": [{ "city": "Hyderabad", "state": "Telangana" }],
  "experience": { "min_years": 8, "max_years": 12 },
  "category": "Data Science & Analytics",
  "recruiter": { "name": "Pradeep Kumar Kannekanti", "designation": "Recruiting Specialist", "company_name": "Google" },
  "company": {
    "id": 5186,
    "name": "Google",
    "ratings": { "source": "glassdoor", "overall": 4.4, "culture_values": 4.2, "recommend_to_friend": 4.3 },
    "benefits": ["Health insurance", "Free meals", "Gym in office", "Team offsites", "Parties"],
    "jobs_count": 30
  }
}
```

All 12 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

12 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | The full job ad, recruiter, posting date and company ratings |
| Company Details | `/companies/details` | Glassdoor ratings, benefits, tech stack, socials, photos and open jobs |
| Autocomplete | `/autocomplete` | Skill, company and location suggestions with filter-ready values |
| Search Jobs | `/jobs/search` | 35 jobs per page with every filter and facet counts |
| Job Stats | `/jobs/stats` | Job counts by type, size, function, industry, company and city |
| Batch Job Details | `/jobs/batch` | Full details for up to 10 jobs in one call |
| Similar Jobs | `/jobs/similar` | 10 similar jobs Instahyre recommends for any job |
| Search Companies | `/companies/search` | Company IDs by name, ready for Company Details |
| Company Jobs | `/companies/jobs` | Every open job at one company, 35 per page |
| Job Functions | `/job-functions` | All 107 job functions in 19 categories |
| Industries | `/industries` | All 74 industries with their IDs |
| Locations | `/locations` | 290+ cities and regions grouped by state, plus remote |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-instahyre-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-instahyre-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-instahyre-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "python", "location": "Bangalore"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Instahyre Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Instahyre%20Scraper%20API.)

[![Ask Us by Email about Instahyre Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Instahyre%20Scraper%20API&body=I%20need%20help%20using%20the%20Instahyre%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**JobStreet Scraper**](https://github.com/omkarcloud/jobstreet-scraper) — JobStreet & JobsDB jobs, salaries, companies & reviews across 6 Asian markets
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/instahyre-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/instahyre-scraper)
