import time

import requests

from app_logging import get_logger

logger = get_logger()

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SEC = 1.0
RETRY_STATUS_CODES = {429, 502, 503, 504}


def post_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    data=None,
    files=None,
    params: dict | None = None,
    timeout: int = 60,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> requests.Response:
    last_response: requests.Response | None = None
    for attempt in range(max_retries):
        resp = requests.post(
            url,
            headers=headers,
            json=json,
            data=data,
            files=files,
            params=params,
            timeout=timeout,
        )
        last_response = resp
        if resp.status_code not in RETRY_STATUS_CODES:
            return resp
        wait = min(DEFAULT_BACKOFF_SEC * (2**attempt), 30.0)
        logger.warning(
            "HTTP %s from %s; retry %s/%s in %.1fs",
            resp.status_code,
            url,
            attempt + 1,
            max_retries,
            wait,
        )
        if attempt + 1 < max_retries:
            time.sleep(wait)
    if last_response is not None:
        return last_response
    raise RuntimeError("post_with_retry: no response")
