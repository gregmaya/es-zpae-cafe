"""
Shared helpers for querying datos.madrid.es's CKAN datastore API
(https://datos.madrid.es/api/3/action/datastore_search_sql). The API
caps rows per request and doesn't error on truncation -- the same
failure mode as the ArcGIS `exceededTransferLimit` bug found in Stage 1
(scripts/01_fetch_zpae.py) -- so callers MUST rely on
assert_pagination_complete rather than trusting a short final page to
mean "done".
"""

from typing import Callable

import requests
from shapely.geometry import Point

SQL_ENDPOINT = "https://datos.madrid.es/api/3/action/datastore_search_sql"


def assert_pagination_complete(fetched_count: int, reported_total: int) -> None:
    """Raise if a paginated fetch stopped short of the API's reported
    total row count."""
    if fetched_count != reported_total:
        raise ValueError(
            f"Pagination incomplete: fetched {fetched_count} rows but "
            f"the API reports {reported_total} total -- a page was "
            f"dropped or the loop stopped early."
        )


def build_point_geometry(x: str, y: str) -> Point:
    """Build a shapely Point from the censo de locales'
    coordenada_x_local/coordenada_y_local string fields."""
    return Point(float(x), float(y))


def fetch_all_records(
    resource_id: str,
    where_sql: str,
    page_size: int = 1000,
    http_post: Callable[..., "requests.Response"] = requests.post,
) -> list[dict]:
    """Fetch every row matching where_sql from a CKAN datastore resource,
    paginating with LIMIT/OFFSET until the fetched count matches the
    API's reported total. `http_post` is injectable for testing."""
    records: list[dict] = []
    offset = 0
    total = None
    while True:
        sql = (
            f'SELECT * FROM "{resource_id}" WHERE {where_sql} '
            f"LIMIT {page_size} OFFSET {offset}"
        )
        resp = http_post(SQL_ENDPOINT, data={"sql": sql}, timeout=60)
        resp.raise_for_status()
        page = resp.json()["result"]["records"]
        records.extend(page)

        if total is None:
            count_sql = f'SELECT COUNT(*) FROM "{resource_id}" WHERE {where_sql}'
            count_resp = http_post(SQL_ENDPOINT, data={"sql": count_sql}, timeout=60)
            count_resp.raise_for_status()
            total = int(count_resp.json()["result"]["records"][0]["count"])

        if not page or len(records) >= total:
            break
        offset += page_size

    assert_pagination_complete(len(records), total)
    return records
