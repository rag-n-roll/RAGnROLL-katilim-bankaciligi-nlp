import ssl
import subprocess
import sys

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
    result = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
