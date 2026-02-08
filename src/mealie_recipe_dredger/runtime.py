import logging
import random
import signal
import time
from typing import Dict
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DEFAULT_CRAWL_DELAY, RESPECT_ROBOTS_TXT

logger = logging.getLogger("dredger")


class GracefulKiller:
    """Catches Docker stop signals to allow safe shutdown."""

    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, _frame):
        signal_name = "SIGINT (Ctrl+C)" if signum == signal.SIGINT else "SIGTERM (Docker Stop)"
        logger.info(f"🛑 Received {signal_name}. Initiating graceful shutdown...")
        self.kill_now = True


def get_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504, 429],
        allowed_methods=["HEAD", "GET"],
    )
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class RateLimiter:
    def __init__(self):
        self.last_request: Dict[str, float] = {}
        self.crawl_delays: Dict[str, float] = {}
        self.session = get_session()

    def get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def get_crawl_delay(self, domain: str) -> float:
        if domain in self.crawl_delays:
            return self.crawl_delays[domain]

        delay = DEFAULT_CRAWL_DELAY
        if RESPECT_ROBOTS_TXT:
            try:
                response = self.session.get(f"https://{domain}/robots.txt", timeout=5)
                if response.status_code == 200:
                    for line in response.text.splitlines():
                        if line.lower().startswith("crawl-delay:"):
                            try:
                                delay = float(line.split(":", 1)[1].strip())
                                break
                            except ValueError:
                                pass
            except Exception:
                pass

        self.crawl_delays[domain] = delay
        return delay

    def wait_if_needed(self, url: str):
        domain = self.get_domain(url)
        delay = self.get_crawl_delay(domain)

        if domain in self.last_request:
            elapsed = time.time() - self.last_request[domain]
            if elapsed < delay:
                jitter = random.uniform(0.5, 1.5)
                sleep_time = (delay - elapsed) * jitter
                time.sleep(sleep_time)

        self.last_request[domain] = time.time()
