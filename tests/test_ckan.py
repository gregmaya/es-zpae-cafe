import pytest

from ckan import assert_pagination_complete, build_point_geometry, fetch_all_records


def test_assert_pagination_complete_passes_when_equal():
    assert_pagination_complete(100, 100)  # no exception


def test_assert_pagination_complete_raises_when_mismatched():
    with pytest.raises(ValueError):
        assert_pagination_complete(50, 100)


def test_build_point_geometry():
    point = build_point_geometry("440554.59", "4475338.53")
    assert point.x == 440554.59
    assert point.y == 4475338.53


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_http_post_factory(pages, total):
    """Serves `pages` (a list of record-lists) in sequence for successive
    LIMIT/OFFSET calls, and answers COUNT(*) queries with `total`."""
    calls = {"n": 0}

    def fake_post(url, data, timeout):
        sql = data["sql"]
        if sql.startswith("SELECT COUNT(*)"):
            return _FakeResponse({"result": {"records": [{"count": total}]}})
        idx = calls["n"]
        calls["n"] += 1
        page = pages[idx] if idx < len(pages) else []
        return _FakeResponse({"result": {"records": page}})

    return fake_post


def test_fetch_all_records_paginates_until_total_reached():
    pages = [
        [{"id": 1}, {"id": 2}],
        [{"id": 3}],
    ]
    fake_post = _fake_http_post_factory(pages, total=3)

    records = fetch_all_records(
        "some-resource", "1=1", page_size=2, http_post=fake_post
    )

    assert records == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_fetch_all_records_raises_if_total_not_reached():
    pages = [[{"id": 1}, {"id": 2}]]
    fake_post = _fake_http_post_factory(pages, total=5)

    with pytest.raises(ValueError):
        fetch_all_records("some-resource", "1=1", page_size=2, http_post=fake_post)
