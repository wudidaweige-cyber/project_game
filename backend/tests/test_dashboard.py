"""Dashboard API smoke tests (require seeded DB + auth)."""

from datetime import date, timedelta


def test_overview_returns_core_metrics(client, auth_headers):
    end = date.today()
    start = end - timedelta(days=7)
    resp = client.get(
        "/api/v1/dashboard/overview",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    for key in (
        "gmv",
        "order_count",
        "rent_rate",
        "refund_rate",
        "available_account_count",
        "active_game_count",
    ):
        assert key in data


def test_trends_and_rank(client, auth_headers):
    end = date.today()
    start = end - timedelta(days=14)
    trends = client.get(
        "/api/v1/dashboard/trends",
        params={
            "metric": "gmv",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        headers=auth_headers,
    ).json()
    assert trends["code"] == 200
    assert isinstance(trends["data"]["points"], list)
    assert len(trends["data"]["points"]) >= 1

    rank = client.get(
        "/api/v1/dashboard/game-rank",
        params={
            "metric": "gmv",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "limit": 5,
        },
        headers=auth_headers,
    ).json()
    assert rank["code"] == 200
    assert len(rank["data"]["items"]) >= 1
    assert "game_name" in rank["data"]["items"][0]
