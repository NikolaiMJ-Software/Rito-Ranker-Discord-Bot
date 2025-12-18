import aiohttp
from urllib.parse import quote

class RiotNotFound(Exception): ...
class RiotUnauthorized(Exception): ...
class RiotRateLimited(Exception):
    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after

async def get_puuid_by_riot_id(api_key: str, riot_id: str, region_cluster: str = "europe"):
    api_key = (api_key or "").strip()
    if not api_key:
        raise RiotUnauthorized()

    # riot_id: "GameName#TAG"
    if "#" not in riot_id:
        raise RiotNotFound()

    game_name, tag_line = riot_id.split("#", 1)
    game_name = quote(game_name.strip(), safe="")
    tag_line = quote(tag_line.strip(), safe="")

    url = f"https://{region_cluster}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()

            # ✅ DEBUG: print the real result from Riot
            print(f"[RiotAPI] GET {url} -> {resp.status} | body={text[:200]}")

            if resp.status == 200:
                data = await resp.json()
                return data["puuid"], data["gameName"], data["tagLine"]

            if resp.status in (401, 403):
                raise RiotUnauthorized()

            if resp.status == 404:
                raise RiotNotFound()

            if resp.status == 429:
                ra = resp.headers.get("Retry-After")
                raise RiotRateLimited(int(ra) if ra and ra.isdigit() else None)

            resp.raise_for_status()

