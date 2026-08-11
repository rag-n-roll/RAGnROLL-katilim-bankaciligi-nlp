"""Kibar ve tekrar denemeli HTTP istemcisi."""

from __future__ import annotations

import logging
import ssl
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import truststore
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGER = logging.getLogger(__name__)
DEFAULT_USER_AGENT = (
    "RAGnROLLCampaignBot/1.0 "
    "(+https://github.com/rag-n-roll/RAGnROLL-katilim-bankaciligi-nlp)"
)


class TruststoreHTTPAdapter(HTTPAdapter):
    """Sistem CA deposunu yalnizca bagli oldugu requests oturumunda kullanir."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        super().__init__(*args, **kwargs)

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: object,
    ) -> None:
        pool_kwargs.setdefault("ssl_context", self._ssl_context)
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: object):  # type: ignore[no-untyped-def]
        proxy_kwargs.setdefault("ssl_context", self._ssl_context)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


class RobotsDeniedError(PermissionError):
    """robots.txt bir URL'nin taranmasina izin vermediginde olusur."""


class HttpClient:
    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 25.0,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
    ) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self._last_request_at: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            }
        )
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        # Global ssl monkey-patch'i yerine sistem guven deposu bu oturuma ozeldir.
        self.session.mount("https://", TruststoreHTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def _robot_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser(robots_url)
        try:
            response = self.session.get(robots_url, timeout=self.timeout_seconds)
            if response.status_code >= 400:
                LOGGER.warning(
                    "robots.txt okunamadi (%s): HTTP %s",
                    robots_url,
                    response.status_code,
                )
                self._robots[origin] = None
                return None
            parser.parse(response.text.splitlines())
        except requests.RequestException as exc:
            LOGGER.warning("robots.txt okunamadi (%s): %s", robots_url, exc)
            self._robots[origin] = None
            return None
        self._robots[origin] = parser
        return parser

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_request_at.get(host, 0.0)
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def get(self, url: str) -> requests.Response:
        if self.respect_robots:
            parser = self._robot_parser(url)
            if parser is not None and not parser.can_fetch(self.user_agent, url):
                raise RobotsDeniedError(f"robots.txt taramaya izin vermiyor: {url}")
        self._throttle(url)
        response = self.session.get(url, timeout=self.timeout_seconds)
        self._last_request_at[urlparse(url).netloc] = time.monotonic()
        response.raise_for_status()
        return response

    def get_text(self, url: str) -> str:
        text, _ = self.get_text_with_url(url)
        return text

    def get_text_with_url(self, url: str) -> tuple[str, str]:
        """Metni ve yonlendirmelerden sonraki kanonik yanit URL'sini dondurur."""
        response = self.get(url)
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text, response.url
