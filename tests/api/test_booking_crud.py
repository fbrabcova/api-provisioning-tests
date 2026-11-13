"""API tests against the real Restful Booker service (integration / end-to-end level).

Every test checks the result (test oracle), not just the status code.
"""

import pytest

from booker.data import make_booking_data

pytestmark = pytest.mark.api


def test_created_booking_is_stored_exactly_as_sent(client, booking):
    booking_id, data = booking
    r = client.get_booking(booking_id)
    assert r.status_code == 200
    assert r.json() == data


def test_booking_can_be_found_by_query_parameters(client, booking):
    booking_id, data = booking
    assert booking_id in client.find_bookings(data["firstname"], data["lastname"])


def test_patch_changes_only_the_field_that_was_sent(client, booking):
    booking_id, data = booking
    r = client.patch_booking(booking_id, {"additionalneeds": "Late checkout"})
    assert r.status_code == 200

    stored = client.get_booking(booking_id).json()
    assert stored["additionalneeds"] == "Late checkout"
    for field in ("firstname", "lastname", "totalprice", "depositpaid", "bookingdates"):
        assert stored[field] == data[field], "PATCH must not touch %s" % field


def test_put_replaces_the_whole_booking(client, booking):
    booking_id, _ = booking
    new_data = make_booking_data(prefix="put")
    r = client.update_booking(booking_id, new_data)
    assert r.status_code == 200
    assert client.get_booking(booking_id).json() == new_data


def test_put_with_missing_fields_is_rejected(client, booking):
    """PUT means 'replace everything', so an incomplete body should not be accepted."""
    booking_id, data = booking
    r = client.update_booking(booking_id, {"firstname": "only-name"})
    assert r.status_code == 400
    assert client.get_booking(booking_id).json() == data, "rejected PUT must not change data"


def test_update_without_token_is_refused(anonymous_client, booking):
    booking_id, _ = booking
    r = anonymous_client.update_booking(booking_id, make_booking_data())
    # HTTP says 401 for missing credentials; Restful Booker is documented to answer 403.
    assert r.status_code in (401, 403)


def test_deleted_booking_is_gone(client):
    booking_id = client.create_booking(make_booking_data())
    r = client.delete_booking(booking_id)
    assert r.status_code in (200, 201, 204)
    assert client.get_booking(booking_id).status_code == 404


def test_unknown_booking_returns_404(client):
    assert client.get_booking(999999999).status_code == 404
