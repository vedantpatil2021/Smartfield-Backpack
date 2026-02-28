import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)
_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()


async def post(url: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            async with get_session().post(url, params=params) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("POST %s failed (attempt %d): %s — retry in %ds", url, attempt + 1, e, wait)
            if attempt < retries - 1:
                await asyncio.sleep(wait)
    raise RuntimeError(f"POST {url} failed after {retries} attempts")


async def get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            async with get_session().get(url) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("GET %s failed (attempt %d): %s — retry in %ds", url, attempt + 1, e, wait)
            if attempt < retries - 1:
                await asyncio.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries} attempts")
