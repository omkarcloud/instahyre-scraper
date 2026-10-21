"""Configuration for the Instahyre Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT             port the API listens on (default 8000)
    INSTAHYRE_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                     (default: none — direct). Instahyre's JSON API answers
                     plain HTTP with no cookies and no login, so you don't need
                     this for normal use. Its job search allows about 50 calls
                     a minute per IP; set a rotating proxy here only if you
                     start seeing HTTP 429 at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

INSTAHYRE_PROXY = os.environ.get("INSTAHYRE_PROXY") or None

# Names the instahyre package reads.
INSTAHYRE_ALLOW_DIRECT = True               # no INSTAHYRE_PROXY set -> connect directly from this machine
INSTAHYRE_PROXY_COUNTRY = None              # unused here: INSTAHYRE_PROXY above is the whole proxy policy
INSTAHYRE_MAX_ATTEMPTS = MAX_RETRIES        # attempts per upstream call
INSTAHYRE_WORKERS = 6                       # parallel upstream calls in /jobs/search?include_details and /jobs/batch


def instahyre_proxy(fallback=False):
    """The proxy for one Instahyre request: INSTAHYRE_PROXY, or None for direct."""
    return os.environ.get("INSTAHYRE_PROXY") or None
