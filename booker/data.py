"""Test data with unique names, so parallel runs and other users never collide."""

import uuid


def make_booking_data(prefix="qa"):
    return {
        "firstname": "%s-%s" % (prefix, uuid.uuid4().hex[:8]),
        "lastname": "Tester",
        "totalprice": 150,
        "depositpaid": True,
        "bookingdates": {"checkin": "2027-01-10", "checkout": "2027-01-12"},
        "additionalneeds": "Breakfast",
    }
