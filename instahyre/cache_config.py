"""Cache TTL per /instahyre/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so an omitted param and its default
share a row).

Instahyre's search index moves hourly (new ads, closures, re-ranking); one
ad changes rarely once posted (its posting date never); company pages move
daily at most; the lookup lists are stable for weeks."""
from datetime import timedelta

# --- raw upstream payloads shared by several routes (fetch.shared_raw) ----------
COMPANY_ID_CACHE = timedelta(days=30)        # company slug / name -> employer id (never changes)
LOOKUP_RAW_CACHE = timedelta(days=1)         # the job function / industry / location lists

# --- jobs -----------------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
STATS_CACHE = timedelta(hours=3)
JOB_CACHE = timedelta(hours=6)
SIMILAR_CACHE = timedelta(hours=6)

# --- companies ----------------------------------------------------------------------------
COMPANY_CACHE = timedelta(days=1)
COMPANY_SEARCH_CACHE = timedelta(days=1)

# --- lookups ------------------------------------------------------------------------------
LOOKUPS_CACHE = timedelta(days=1)
AUTOCOMPLETE_CACHE = timedelta(days=7)
