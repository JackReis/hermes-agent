from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"


def test_mission_control_is_first_class_dashboard_surface():
    app = (WEB / "App.tsx").read_text()
    page = WEB / "pages" / "MissionControlPage.tsx"

    assert page.exists()
    page_text = page.read_text()

    assert '"/mission-control": MissionControlPage' in app
    assert 'to="/mission-control"' in app or 'path: "/mission-control"' in app
    assert 'Navigate to="/mission-control"' in app
    assert "Mission Control" in app

    assert "Mission Control" in page_text
    assert "Hermes is the cockpit" in page_text
    assert "Olympus is deprecated" in page_text
    assert "api.getStatus()" in page_text
    assert "gateway_platforms" in page_text
    assert "Projection health" in page_text
    assert "/sinew/api/sinew" in page_text
    assert "AbortController" in page_text
    assert "Sinew check timed out" in page_text
    assert "api.getMissionControlForest()" in page_text
    assert "Infrastructure map" in page_text
    assert "Remote access" in page_text
    assert "Agent lanes" in page_text
    assert "Ownership rules" in page_text
    assert "Context freshness" in page_text
    assert "Matrix" in page_text
    assert "Telegram" in page_text
    assert "Mattermost" in page_text
    assert "Mission Control absorbs the useful Olympus projections" in page_text
    assert "http://127.0.0.1:3020" in page_text
    assert "http://127.0.0.1:8081" in page_text
