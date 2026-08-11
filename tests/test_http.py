import subprocess
import sys

import requests

from src.scraper.http import HttpClient, TruststoreHTTPAdapter


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
