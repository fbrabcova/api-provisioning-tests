"""Unit tests: no network, no server. Everything outside the code is replaced by fakes."""

from unittest import mock

import pytest
import requests

from booker.client import BookerClient, wait_until, with_retry


def test_retry_succeeds_after_transient_errors_with_exponential_backoff():
    calls, waits = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("network down")
        return "ok"

    assert with_retry(flaky, retries=3, backoff_s=1.0, sleep=waits.append) == "ok"
    assert len(calls) == 3
    assert waits == [1.0, 2.0]


def test_retry_gives_up_and_reraises_the_last_error():
    def always_down():
        raise requests.Timeout("too slow")

    with pytest.raises(requests.Timeout):
        with_retry(always_down, retries=3, sleep=lambda s: None)


def test_retry_does_not_repeat_non_transient_errors():
    calls = []

    def bug():
        calls.append(1)
        raise ValueError("bad data")

    with pytest.raises(ValueError):
        with_retry(bug, retries=3, sleep=lambda s: None)
    assert len(calls) == 1


def test_wait_until_polls_until_the_condition_is_true():
    answers = iter([False, False, True])
    now = [0.0]

    def fake_sleep(s):
        now[0] += s

    assert wait_until(lambda: next(answers), timeout_s=10, interval_s=2,
                      clock=lambda: now[0], sleep=fake_sleep)
    assert now[0] == 4.0


def test_wait_until_times_out_in_seconds():
    now = [0.0]

    def fake_sleep(s):
        now[0] += s

    with pytest.raises(TimeoutError):
        wait_until(lambda: False, timeout_s=5, interval_s=1,
                   clock=lambda: now[0], sleep=fake_sleep)
    assert now[0] == 5.0


def _client():
    c = BookerClient("https://example.invalid")
    c._sleep = lambda s: None
    return c


def test_create_does_not_duplicate_when_first_attempt_already_saved_the_booking():
    c = _client()
    data = {"firstname": "qa-1", "lastname": "Tester"}
    with mock.patch.object(c, "_request", side_effect=requests.Timeout("lost answer")) as post, \
         mock.patch.object(c, "find_bookings", return_value=[42]):
        assert c.create_booking(data) == 42
    assert post.call_count == 1  # no second POST, so no duplicate


def test_create_retries_when_nothing_was_saved():
    c = _client()
    data = {"firstname": "qa-2", "lastname": "Tester"}
    ok = mock.Mock(status_code=200)
    ok.json.return_value = {"bookingid": 7}
    with mock.patch.object(c, "_request", side_effect=[requests.Timeout("lost"), ok]) as post, \
         mock.patch.object(c, "find_bookings", return_value=[]):
        assert c.create_booking(data) == 7
    assert post.call_count == 2
