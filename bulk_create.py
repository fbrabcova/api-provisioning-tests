#!/usr/bin/env python3
"""Bulk-create N bookings, verify each one, write a JUnit report, clean up.

Exit code 0 only if every booking was created AND verified. Nothing is swallowed:
every failure is recorded in the report and changes the exit code.
"""

import argparse
import logging
import os
import sys
import time
from xml.sax.saxutils import quoteattr

from booker.client import DEFAULT_BASE_URL, BookerClient
from booker.data import make_booking_data

log = logging.getLogger("bulk")


def write_junit(path, results):
    failures = sum(1 for r in results if r["error"])
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<testsuite name="bulk-create" tests="%d" failures="%d">' % (len(results), failures)]
    for r in results:
        lines.append('  <testcase classname="bulk_create" name=%s time="%.2f">'
                     % (quoteattr(r["name"]), r["seconds"]))
        if r["error"]:
            lines.append("    <failure message=%s/>" % quoteattr(r["error"]))
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--prefix", default="bulk")
    ap.add_argument("--base-url", default=os.environ.get("BOOKER_URL", DEFAULT_BASE_URL))
    ap.add_argument("--ready-timeout-s", type=float, default=90.0)
    ap.add_argument("--junit", default="results/bulk.xml")
    ap.add_argument("--keep", action="store_true", help="do not delete created bookings")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = BookerClient(args.base_url)
    client.wait_until_ready(timeout_s=args.ready_timeout_s)
    client.authenticate(os.environ.get("BOOKER_USER", "admin"),
                        os.environ.get("BOOKER_PASSWORD", "password123"))

    results, created = [], []
    for i in range(1, args.count + 1):
        data = make_booking_data(prefix=args.prefix)
        t0 = time.monotonic()
        error = ""
        try:
            booking_id = client.create_booking(data)
            created.append(booking_id)
            stored = client.get_booking(booking_id)
            if stored.status_code != 200 or stored.json() != data:  # test oracle
                error = "booking %s not stored as sent" % booking_id
        except Exception as exc:  # recorded below, never silently ignored
            error = "%s: %s" % (type(exc).__name__, exc)
        results.append({"name": data["firstname"], "error": error,
                        "seconds": time.monotonic() - t0})
        log.info("[%d/%d] %s %s", i, args.count, data["firstname"], error or "OK")

    if not args.keep:
        for booking_id in created:
            r = client.delete_booking(booking_id)
            if r.status_code not in (200, 201, 204):
                log.error("cleanup of %s failed: HTTP %d", booking_id, r.status_code)

    write_junit(args.junit, results)
    failed = sum(1 for r in results if r["error"])
    log.info("done: %d OK / %d FAIL", len(results) - failed, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
