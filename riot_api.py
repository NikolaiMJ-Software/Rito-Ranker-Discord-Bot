import aiohttp
from urllib.parse import quote

class RiotAPIError(Exception):
    pass

class RiotNotFound(RiotAPIError):
    pass

class RiotUnauthorized(RiotAPIError):
    pass

class RiotRateLimited(RiotAPIError):
    def __init__(self, retry_after: float | None = None):
        super().__init__("Rate limited")
        self.retry_after = retry_after

async def get_puuid_by_riot_id(api_key: str, riot_id: str, region_cluster: str = "europe") -> tuple[str, str, str]:
    """
    Returns (puuid, gameName, tagLine) for a Riot ID like 'GameName#TAG'.

    region_cluster: 'americas' | 'asia' | 'europe'
    Account-V1 supports these routing values and can query any account; using nearest is recommended. :contentReference[oaicite:1]{index=1}
    """
    if "#" not in riot_id:
        raise ValueError("Riot ID must look like GameName#TAG")

    game_name, tag_line = riot_id.split("#", 1)
    game_name = game_name.strip()
    tag_line = tag_line.strip()

    if not game_name or not tag_line:
        raise ValueError("Riot ID must look like GameName#TAG")

    # URL encode (names can include spaces/special chars)
    game_q = quote(game_name, safe="")
    tag_q = quote(tag_line, safe="")

    url = f"https://{region_cluster}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_q}/{tag_q}"
    headers = {"X-Riot-Token": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["puuid"], data["gameName"], data["tagLine"]

            if resp.status == 401 or resp.status == 403:
                raise RiotUnauthorized(f"Riot API auth error ({resp.status})")

            if resp.status == 404:
                raise RiotNotFound("Riot ID not found")

            if resp.status == 429:
                retry_after = resp.headers.get("Retry-After")
                raise RiotRateLimited(float(retry_after) if retry_after else None)

            text = await resp.text()
            raise RiotAPIError(f"Riot API error {resp.status}: {text[:200]}")
