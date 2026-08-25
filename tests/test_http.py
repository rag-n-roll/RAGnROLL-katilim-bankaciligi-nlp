import subprocess
import sys
import time

import pytest
import requests

from src.scraper.http import HttpClient, RobotsDeniedError, TruststoreHTTPAdapter


def _response(status_code=200, url="https://bank.example/robots.txt", text=""):
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response._content = text.encode()
    response.encoding = "utf-8"
    return response


def test_http_client_scopes_truststore_to_https_session():
    client = HttpClient(respect_robots=False)
    assert isinstance(client.session.get_adapter("https://"), TruststoreHTTPAdapter)


def test_import_does_not_replace_global_ssl_context():
    code = (
        "import ssl; original = ssl.SSLContext; "
        "import src.scraper.http; "
        "assert ssl.SSLContext is original"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_get_text_with_url_returns_redirect_target(monkeypatch):
    client = HttpClient(respect_robots=False)
    response = requests.Response()
    response.status_code = 200
    response.url = "https://campaigns.example/kampanyalar"
    response._content = "Kampanyalar".encode()
    response.encoding = "utf-8"
    monkeypatch.setattr(client, "get", lambda _url: response)

    assert client.get_text_with_url("https://bank.example/kampanyalar") == (
        "Kampanyalar",
        "https://campaigns.example/kampanyalar",
    )


def test_robot_parser_fetches_and_caches(monkeypatch):
    client = HttpClient(respect_robots=True)
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _response(text="User-agent: *\nDisallow:\n")

    monkeypatch.setattr(client.session, "get", fake_get)

    parser_first = client._robot_parser("https://bank.example/kampanyalar")
    parser_second = client._robot_parser("https://bank.example/diger")
    assert parser_first is parser_second
    assert calls == ["https://bank.example/robots.txt"]
    assert parser_first.can_fetch(client.user_agent, "https://bank.example/kampanyalar")


def test_robot_parser_handles_http_error_and_caches_none(monkeypatch, caplog):
    client = HttpClient(respect_robots=True)
    monkeypatch.setattr(
        client.session, "get", lambda url, **kwargs: _response(status_code=404)
    )

    assert client._robot_parser("https://bank.example/x") is None
    assert client._robot_parser("https://bank.example/y") is None
    assert "robots.txt okunamadi" in caplog.text


def test_robot_parser_handles_request_exception(monkeypatch, caplog):
    client = HttpClient(respect_robots=True)

    def fail(url, **kwargs):
        raise requests.ConnectionError("baglanti hatasi")

    monkeypatch.setattr(client.session, "get", fail)

    assert client._robot_parser("https://unreachable.example/x") is None
    assert "robots.txt okunamadi" in caplog.text


def test_get_raises_when_robots_denies(monkeypatch):
    client = HttpClient(respect_robots=True)
    monkeypatch.setattr(
        client.session,
        "get",
        lambda url, **kwargs: _response(text="User-agent: *\nDisallow: /\n"),
    )

    with pytest.raises(RobotsDeniedError, match="robots.txt taramaya izin vermiyor"):
        client.get("https://blocked.example/kampanyalar")


def test_get_skips_robots_check_when_disabled(monkeypatch):
    client = HttpClient(respect_robots=False)
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _response(url=url)

    monkeypatch.setattr(client.session, "get", fake_get)
    response = client.get(
        "https://bank.example/api", params={"sayfa": 2}, headers={"X-Test": "1"}
    )

    assert response.status_code == 200
    assert seen["url"] == "https://bank.example/api"
    assert seen["kwargs"]["params"] == {"sayfa": 2}
    assert seen["kwargs"]["headers"] == {"X-Test": "1"}
    assert "robots" not in seen["url"]


def test_throttle_sleeps_within_delay_window(monkeypatch):
    client = HttpClient(respect_robots=False, delay_seconds=2.0)
    host = "throttled.example"
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    client._last_request_at[host] = time.monotonic()

    client._throttle(f"https://{host}/kampanyalar")

    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 2.0


def test_throttle_does_not_sleep_after_delay_elapsed(monkeypatch):
    client = HttpClient(respect_robots=False, delay_seconds=0.5)
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    client._last_request_at["old.example"] = time.monotonic() - 10

    client._throttle("https://old.example/kampanyalar")

    assert sleeps == []


class _FakeResponse:
    def __init__(self, url, text, encoding, apparent_encoding=None):
        self.url = url
        self.text = text
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding


def test_get_text_falls_back_to_apparent_encoding(monkeypatch):
    client = HttpClient(respect_robots=False)
    response = _FakeResponse(
        "https://bank.example/kampanyalar", "Kampanyalar", None, "utf-8"
    )
    monkeypatch.setattr(client, "get", lambda _url: response)

    assert client.get_text("https://bank.example/kampanyalar") == "Kampanyalar"
    assert response.encoding == "utf-8"


def test_get_text_replaces_default_iso_8859_1_encoding(monkeypatch):
    client = HttpClient(respect_robots=False)
    response = _FakeResponse(
        "https://bank.example/kampanyalar", "Kampanyalar", "ISO-8859-1"
    )
    monkeypatch.setattr(client, "get", lambda _url: response)

    text, final_url = client.get_text_with_url("https://bank.example/kampanyalar")
    assert text == "Kampanyalar"
    assert response.encoding == "utf-8"
    assert final_url == "https://bank.example/kampanyalar"


def test_get_propagates_http_errors(monkeypatch):
    client = HttpClient(respect_robots=False)
    response = _response(status_code=500)
    monkeypatch.setattr(client.session, "get", lambda url, **kwargs: response)

    with pytest.raises(requests.HTTPError):
        client.get("https://broken.example/")
