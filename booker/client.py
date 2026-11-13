"""Small client for the public Restful Booker API (https://restful-booker.herokuapp.com).

Design rules (each one fixes a problem found in a real-world test suite):
  * Retry only idempotent requests (GET, PUT, DELETE) blindly.
  * POST is not idempotent: before retrying it, check whether the first attempt
    already created the record, so a retry never creates a duplicate.
  * Wait for a state (polling) instead of sleeping a fixed time.
  * Every timeout is in seconds and its name says so (``*_s``).
"""

import logging
import time

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://restful-booker.herokuapp.com"


class ApiError(Exception):
    """The API answered, but not the way the client expected."""


class TransientError(ApiError):
    """A server-side error (5xx) that may go away if we try again."""


TRANSIENT = (requests.ConnectionError, requests.Timeout, TransientError)


def with_retry(fn, retries=3, backoff_s=1.0, retry_on=TRANSIENT, sleep=time.sleep):
    """Call ``fn()``; on a transient error wait 1, 2, 4 ... x backoff_s and try again.

    Use only for idempotent operations. Any other exception is raised at once.
    """
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except retry_on as exc:
            if attempt == retries:
                raise
            wait_s = backoff_s * 2 ** (attempt - 1)
            log.warning("attempt %d/%d failed (%s), retrying in %.1f s",
                        attempt, retries, exc, wait_s)
            sleep(wait_s)


def wait_until(predicate, timeout_s, interval_s=1.0, clock=time.monotonic, sleep=time.sleep):
    """Poll ``predicate()`` until it returns True or ``timeout_s`` seconds pass."""
    deadline = clock() + timeout_s
    while True:
        if predicate():
            return True
        if clock() >= deadline:
            raise TimeoutError("condition not met within %s s" % timeout_s)
        sleep(interval_s)


class BookerClient:
    def __init__(self, base_url=DEFAULT_BASE_URL, timeout_s=15.0, retries=3, backoff_s=1.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = retries
        self.backoff_s = backoff_s
        self._sleep = time.sleep  # replaced by a no-op in unit tests
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",  # what we send
            "Accept": "application/json",        # what we want back
        })

    # -- low level -----------------------------------------------------------

    def _request(self, method, path, **kwargs):
        r = self.session.request(method, self.base_url + path, timeout=self.timeout_s, **kwargs)
        if r.status_code >= 500:
            raise TransientError("%s %s -> HTTP %d" % (method, path, r.status_code))
        return r

    def _retry(self, fn):
        return with_retry(fn, retries=self.retries, backoff_s=self.backoff_s, sleep=self._sleep)

    # -- health and auth -----------------------------------------------------

    def is_ready(self):
        try:
            return self._request("GET", "/ping").status_code == 201
        except (requests.RequestException, TransientError):
            return False

    def wait_until_ready(self, timeout_s=60.0, interval_s=2.0):
        """Free hosting can sleep; poll /ping instead of a fixed sleep."""
        return wait_until(self.is_ready, timeout_s, interval_s, sleep=self._sleep)

    def authenticate(self, username, password):
        # POST /auth only issues a token and changes no data, so a retry is harmless.
        r = self._retry(lambda: self._request(
            "POST", "/auth", json={"username": username, "password": password}))
        token = r.json().get("token")
        if not token:
            raise ApiError("authentication failed: %s" % r.text[:200])
        self.session.headers["Cookie"] = "token=" + token
        return token

    # -- bookings ------------------------------------------------------------

    def get_booking(self, booking_id):
        return self._retry(lambda: self._request("GET", "/booking/%s" % booking_id))

    def find_bookings(self, firstname, lastname):
        """GET /booking?firstname=...&lastname=... (filter via query parameters)."""
        r = self._retry(lambda: self._request(
            "GET", "/booking", params={"firstname": firstname, "lastname": lastname}))
        r.raise_for_status()
        return [item["bookingid"] for item in r.json()]

    def create_booking(self, data):
        """Create a booking and return its id, without ever creating a duplicate."""
        for attempt in range(1, self.retries + 1):
            try:
                r = self._request("POST", "/booking", json=data)
                if r.status_code != 200:
                    raise ApiError("create failed: HTTP %d %s" % (r.status_code, r.text[:200]))
                return r.json()["bookingid"]
            except TRANSIENT as exc:
                # The request may have reached the server before it failed.
                existing = self.find_bookings(data["firstname"], data["lastname"])
                if existing:
                    log.warning("create failed (%s), but booking %s exists; not retrying",
                                exc, existing[0])
                    return existing[0]
                if attempt == self.retries:
                    raise
                self._sleep(self.backoff_s * 2 ** (attempt - 1))

    def update_booking(self, booking_id, data):
        """PUT replaces the whole booking. Idempotent, so it may be retried."""
        return self._retry(lambda: self._request("PUT", "/booking/%s" % booking_id, json=data))

    def patch_booking(self, booking_id, fields):
        """PATCH changes only the fields sent."""
        return self._request("PATCH", "/booking/%s" % booking_id, json=fields)

    def delete_booking(self, booking_id):
        return self._retry(lambda: self._request("DELETE", "/booking/%s" % booking_id))
