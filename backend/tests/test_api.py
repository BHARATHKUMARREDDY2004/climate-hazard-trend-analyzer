import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import cells_for_region
from app.ratelimit import SlidingWindowLimiter
from app.schemas import BoxRegion

POINT = {"type": "point", "lat": 26.92, "lon": 75.79, "label": "Jaipur"}
REQUEST = {"region": POINT, "start_year": 1980, "end_year": 2019}


@pytest.fixture
def client(store, fake_weather, monkeypatch):
    monkeypatch.setattr(main, "general_limiter", SlidingWindowLimiter(1000))
    monkeypatch.setattr(main, "heavy_limiter", SlidingWindowLimiter(1000))
    return TestClient(main.app)


def test_analysis_end_to_end(client, fake_weather):
    response = client.post("/api/analyses", json=REQUEST)
    assert response.status_code == 200
    body = response.json()

    assert body["served_from"] == "computed"
    assert len(body["annual"]) == 40
    assert all(row["complete"] for row in body["annual"])
    assert body["region"]["cells"][0]["lat"] == 26.9
    # the synthetic data warms by 0.5 C per decade
    warming = body["trends"]["mean_tmax"]
    assert warming["direction"] == "increasing"
    assert warming["ols"]["slope"] * 10 == pytest.approx(0.5, abs=0.15)
    assert body["trends"]["days"]["direction"] == "increasing"
    assert body["insights"][0]["kind"] == "headline"
    assert "_id" not in body

    # 5% of days are above the 95th percentile by construction
    hot = sum(row["hot_days"] for row in body["annual"])
    assert hot / body["quality"]["total_days"] == pytest.approx(0.05, abs=0.002)


def test_second_request_is_served_from_the_database(client, fake_weather):
    first = client.post("/api/analyses", json=REQUEST).json()
    second = client.post("/api/analyses", json=REQUEST).json()
    assert second["served_from"] == "database"
    assert second["id"] == first["id"]
    assert len(fake_weather) == 1

    fetched = client.get(f"/api/analyses/{first['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["annual"] == first["annual"]


def test_only_missing_years_are_downloaded(client, fake_weather):
    client.post("/api/analyses", json=REQUEST)
    client.post("/api/analyses", json={**REQUEST, "start_year": 1970})
    assert [(first, last) for _, first, last in fake_weather] == [(1980, 2019), (1970, 1979)]


def test_fixed_baseline_pulls_in_the_baseline_years(client, fake_weather):
    body = client.post(
        "/api/analyses", json={**REQUEST, "start_year": 2000, "baseline": "1961-1990"}
    ).json()
    assert fake_weather[0][1:] == (1961, 2019)
    assert body["params"]["baseline_years"] == [1961, 1990]
    assert len(body["annual"]) == 20


def test_running_year_is_flagged_incomplete_and_left_out_of_trends(client):
    from datetime import date

    this_year = date.today().year
    body = client.post(
        "/api/analyses", json={**REQUEST, "start_year": this_year - 14, "end_year": this_year}
    ).json()
    last = body["annual"][-1]
    if last["coverage"] < 0.9:
        assert last["complete"] is False
        assert body["trends"]["days"]["n"] == 14
        assert this_year in body["quality"]["incomplete_years"]


def test_box_is_sampled_on_a_grid(client):
    box = {"type": "bbox", "south": 23.0, "north": 30.0, "west": 69.5, "east": 78.0, "label": "Rajasthan"}
    body = client.post("/api/analyses", json={**REQUEST, "region": box}).json()
    assert len(body["region"]["cells"]) == 9
    assert body["summary"]["total_events"] is None
    assert any("9 sample points" in i["text"] for i in body["insights"])

    small = BoxRegion(type="bbox", south=10.0, north=10.2, west=20.0, east=20.3)
    assert len(cells_for_region(small)) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"start_year": 1900},
        {"end_year": 2999},
        {"start_year": 2018},
        {"percentile": 50},
        {"min_duration": 1},
        {"hazard": "tsunami"},
        {"threshold_method": "magic"},
        {"unknown_field": 1},
        {"region": {"type": "point", "lat": 95, "lon": 0}},
        {"region": {"type": "point", "lat": "abc", "lon": 0}},
        {"region": {"type": "bbox", "south": 10, "north": 5, "west": 0, "east": 5}},
        {"region": {"type": "bbox", "south": 0, "north": 40, "west": 0, "east": 5}},
        {"region": {"type": "polygon"}},
    ],
)
def test_bad_input_is_rejected(client, fake_weather, patch):
    response = client.post("/api/analyses", json={**REQUEST, **patch})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert fake_weather == []


def test_label_is_sanitised(client):
    region = {**POINT, "label": "  Jaipur\x00\x1b[31m\n  "}
    body = client.post("/api/analyses", json={**REQUEST, "region": region}).json()
    assert body["region"]["label"] == "Jaipur[31m"


def test_analysis_id_must_look_like_an_id(client):
    assert client.get("/api/analyses/not-an-id").status_code == 422
    assert client.get("/api/analyses/0123456789abcdef").status_code == 404


def test_search_rejects_odd_characters(client):
    assert client.get("/api/regions/search", params={"q": "<script>"}).status_code == 422
    assert client.get("/api/regions/search", params={"q": "a"}).status_code == 422


def test_exports(client):
    analysis = client.post("/api/analyses", json=REQUEST).json()
    base = f"/api/analyses/{analysis['id']}"

    annual = client.get(f"{base}/export.csv")
    assert annual.status_code == 200
    assert "attachment" in annual.headers["content-disposition"]
    assert "heatwaves-jaipur-1980-2019-annual.csv" in annual.headers["content-disposition"]
    assert len(annual.text.strip().splitlines()) == 4 + 40

    events = client.get(f"{base}/export.csv", params={"table": "events"})
    assert len(events.text.strip().splitlines()) == 1 + len(analysis["events"])

    pdf = client.get(f"{base}/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    png = client.get(f"{base}/plot.png", params={"metric": "events"})
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")


def test_csv_cells_cannot_become_formulas(client):
    region = {**POINT, "label": "=HYPERLINK(1)"}
    analysis = client.post("/api/analyses", json={**REQUEST, "region": region}).json()
    text = client.get(f"/api/analyses/{analysis['id']}/export.csv").text
    assert "'=HYPERLINK(1)" in text


def test_daily_drill_down(client):
    analysis = client.post("/api/analyses", json=REQUEST).json()
    year = max(analysis["annual"], key=lambda r: r["days"])["year"]
    detail = client.get(f"/api/analyses/{analysis['id']}/daily", params={"year": year}).json()
    assert len(detail["dates"]) == len(detail["tmax"]) == len(detail["threshold"])
    assert detail["events"] and all(e["start"][:4] == str(year) or e["end"][:4] == str(year) for e in detail["events"])

    outside = client.get(f"/api/analyses/{analysis['id']}/daily", params={"year": 1950})
    assert outside.status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main, "heavy_limiter", SlidingWindowLimiter(2))
    codes = [client.post("/api/analyses", json=REQUEST).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    blocked = client.post("/api/analyses", json=REQUEST)
    assert int(blocked.headers["retry-after"]) >= 1


def test_oversized_body_is_refused(client):
    response = client.post("/api/analyses", content=b"x" * 5000, headers={"content-type": "application/json"})
    assert response.status_code == 413
