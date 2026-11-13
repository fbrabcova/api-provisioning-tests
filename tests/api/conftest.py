import os

import pytest

from booker.client import DEFAULT_BASE_URL, BookerClient
from booker.data import make_booking_data

BASE_URL = os.environ.get("BOOKER_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="session")
def client():
    """Logged-in client. Waits (polling) until the API wakes up."""
    c = BookerClient(BASE_URL)
    c.wait_until_ready(timeout_s=90)
    # Public demo credentials from the Restful Booker documentation.
    c.authenticate(os.environ.get("BOOKER_USER", "admin"),
                   os.environ.get("BOOKER_PASSWORD", "password123"))
    return c


@pytest.fixture
def anonymous_client():
    """Client without a token, for negative tests."""
    return BookerClient(BASE_URL)


@pytest.fixture
def booking(client):
    """A fresh booking for one test; deleted afterwards (teardown)."""
    data = make_booking_data()
    booking_id = client.create_booking(data)
    yield booking_id, data
    client.delete_booking(booking_id)
