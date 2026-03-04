"""Weibo content downloader — pure HTTP, no browser dependency.

- Post data: API /ajax/statuses/show
- Comments: API /ajax/statuses/buildComments
- Images: direct CDN download
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field
from rich.console import Console

console = Console()


# ============ Data Models ============

class WeiboUser(BaseModel):
    """Weibo user information."""
    id: str = ""
    screen_name: str = ""
    avatar_hd: str = ""


class WeiboComment(BaseModel):
    """Weibo comment."""
    comment_id: str = ""
    user: WeiboUser = Field(default_factory=WeiboUser)
    text: str = ""
    created_at: str = ""
    likes: int = 0


class WeiboPost(BaseModel):
    """Weibo post."""
    mid: str
    user: WeiboUser = Field(default_factory=WeiboUser)
    text: str = ""
    created_at: str = ""
    reposts_count: int = 0
    comments_count: int = 0
    attitudes_count: int = 0
    images: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    comments: List[WeiboComment] = Field(default_factory=list)


# ============ Downloader ============

class WeiboDownloader:
    """Pure HTTP downloader for Weibo (no Playwright)."""

    BASE_URL = "https://weibo.com"
    DATA_DIR = Path.home() / ".social_media_downloader" / "weibo"

    DETAIL_API = "/ajax/statuses/show"
    COMMENTS_API = "/ajax/statuses/buildComments"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://weibo.com/",
    }

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cookie_path = self.DATA_DIR / "cookies.json"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    # ---- Cookie management ----

    def _load_cookies(self) -> dict:
        """Load cookies as {name: value} dict."""
        if not self.cookie_path.exists():
            return {}

        try:
            with open(self.cookie_path, "r") as f:
                data = json.load(f)

            # Playwright storage_state format
            if isinstance(data, dict) and "cookies" in data:
                cookies = {}
                for c in data["cookies"]:
                    if "weibo" in c.get("domain", ""):
                        cookies[c["name"]] = c["value"]
                return cookies

            # Plain cookie list [{name, value, ...}, ...]
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data}

            return {}
        except Exception:
            return {}

    async def check_login(self) -> bool:
        """Check if cookies exist and are valid."""
        cookies = self._load_cookies()
        if not cookies:
            return False

        # Quick check: try an API endpoint
        try:
            async with httpx.AsyncClient(
                cookies=cookies, headers=self.HEADERS, timeout=10.0
            ) as client:
                response = await client.get(
                    f"{self.BASE_URL}/ajax/side/hotSearch"
                )
                return response.status_code == 200
        except Exception:
            return False

    async def login(self) -> bool:
        """Guide user to import cookies from browser."""
        console.print()
        console.print("[bold cyan]微博 Cookie 导入指南[/bold cyan]")
        console.print()
        console.print("1. 安装浏览器 Cookie 导出插件（推荐 Cookie-Editor 或 Get cookies.txt LOCALLY）")
        console.print("2. 在浏览器中打开 [link=https://weibo.com]weibo.com[/link] 并登录")
        console.print("3. 点击插件图标，导出全部 Cookie（Netscape/txt 或 JSON 格式均可）")
        console.print("4. 粘贴到下面：")
        console.print()

        raw = input("粘贴 Cookie > ").strip()
        if not raw:
            console.print("[red]未输入内容[/red]")
            return False

        try:
            cookies = json.loads(raw)
            if not isinstance(cookies, list):
                raise ValueError("not a list")

            with open(self.cookie_path, "w") as f:
                json.dump(cookies, f, ensure_ascii=False)

            names = {c["name"] for c in cookies}
            if "SUB" in names or "SUBP" in names:
                console.print("[green]Cookie 导入成功！[/green]")
                return True
            else:
                console.print("[yellow]Cookie 已保存，但缺少关键 cookie (SUB/SUBP)[/yellow]")
                console.print("[dim]请确保已登录后再导出[/dim]")
                return False

        except (json.JSONDecodeError, ValueError):
            # Maybe user pasted raw cookie string: "name1=val1; name2=val2"
            if "=" in raw and ";" in raw:
                try:
                    cookies = []
                    for pair in raw.split(";"):
                        pair = pair.strip()
                        if "=" in pair:
                            name, value = pair.split("=", 1)
                            cookies.append({"name": name.strip(), "value": value.strip()})

                    with open(self.cookie_path, "w") as f:
                        json.dump(cookies, f, ensure_ascii=False)

                    console.print("[green]Cookie 导入成功！[/green]")
                    return True
                except Exception:
                    pass

            console.print("[red]无法解析 Cookie，请重试[/red]")
            return False

    def import_cookies(self, raw: str) -> bool:
        """Import cookies from raw string.

        Supports: JSON array, raw cookie string, Netscape cookie file.
        Returns True if essential cookies are present.
        """
        raw = raw.strip()
        if not raw:
            return False

        cookies = _parse_cookies(raw)
        if not cookies:
            return False

        with open(self.cookie_path, "w") as f:
            json.dump(cookies, f, ensure_ascii=False)

        names = {c.get("name", "") for c in cookies}
        return "SUB" in names or "SUBP" in names

    # ---- URL parsing ----

    @staticmethod
    def parse_url(url: str) -> Optional[str]:
        """Extract MID from Weibo URL.

        Supports formats:
        - https://weibo.com/1234567890/AbCdEfGhI
        - https://m.weibo.cn/detail/4567890123456789
        - https://m.weibo.cn/status/4567890123456789
        - Plain MID
        """
        if not url.startswith("http"):
            return url.strip()

        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")

        # Desktop: /uid/mid
        if len(parts) >= 2 and parts[0].isdigit():
            return parts[1]

        # Mobile: /detail/mid or /status/mid
        if len(parts) >= 2 and parts[0] in ("detail", "status"):
            return parts[1]

        # Try last part
        if parts:
            return parts[-1]

        return None

    # ---- Download ----

    async def download(
        self,
        url: str,
        output_dir: Path,
        fetch_comments: bool = True,
        max_comments: int = 50,
        download_images: bool = True,
    ) -> Optional[WeiboPost]:
        """Download a post by URL (pure HTTP)."""
        mid = self.parse_url(url)
        if not mid:
            console.print(f"[red]Invalid URL: {url}[/red]")
            return None

        cookies = self._load_cookies()
        if not cookies:
            console.print("[yellow]未登录，请先导入 Cookie[/yellow]")
            return None

        console.print(f"[cyan]Fetching post: {mid}[/cyan]")

        async with httpx.AsyncClient(
            cookies=cookies,
            headers=self.HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:

            # Fetch post details
            post = await self._fetch_post(client, mid)
            if not post:
                console.print("[red]Failed to fetch post.[/red]")
                return None

            # Fetch comments
            if fetch_comments and post.comments_count > 0:
                post.comments = await self._fetch_comments(
                    client, mid, post.user.id, max_comments
                )
                console.print(f"[green]Fetched {len(post.comments)} comments[/green]")

            # Download images
            if download_images and post.images:
                post_dir = output_dir / mid
                post_dir.mkdir(parents=True, exist_ok=True)
                await self._download_images(post.images, post_dir, client)
                console.print(
                    f"[green]Downloaded {len(post.images)} images to {post_dir}[/green]"
                )

            # Save JSON
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / f"{mid}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(post.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            console.print(f"[green]Saved content to {json_path}[/green]")

            return post

    async def _fetch_post(
        self, client: httpx.AsyncClient, mid: str
    ) -> Optional[WeiboPost]:
        """Fetch post details via API."""
        try:
            response = await client.get(
                f"{self.BASE_URL}{self.DETAIL_API}",
                params={"id": mid, "locale": "zh-CN"},
                timeout=30.0,
            )

            if response.status_code != 200:
                return None

            data = response.json()

            # Extract user
            user_data = data.get("user", {})
            user = WeiboUser(
                id=str(user_data.get("id", "")),
                screen_name=user_data.get("screen_name", ""),
                avatar_hd=user_data.get("avatar_hd", ""),
            )

            # Extract images
            images = []
            pic_infos = data.get("pic_infos", {})
            for pic_id, pic_data in pic_infos.items():
                for size in ["original", "large", "mw2000", "mw1024"]:
                    url = pic_data.get(size, {}).get("url")
                    if url:
                        images.append(url)
                        break

            # Extract video
            video_url = None
            page_info = data.get("page_info", {})
            if page_info.get("type") == "video":
                media_info = page_info.get("media_info", {})
                video_url = (
                    media_info.get("stream_url_hd") or media_info.get("stream_url")
                )

            return WeiboPost(
                mid=mid,
                user=user,
                text=data.get("text_raw", data.get("text", "")),
                created_at=data.get("created_at", ""),
                reposts_count=data.get("reposts_count", 0),
                comments_count=data.get("comments_count", 0),
                attitudes_count=data.get("attitudes_count", 0),
                images=images,
                video_url=video_url,
            )

        except Exception as e:
            console.print(f"[red]Error fetching post: {e}[/red]")
            return None

    async def _fetch_comments(
        self,
        client: httpx.AsyncClient,
        mid: str,
        uid: str,
        max_comments: int,
    ) -> List[WeiboComment]:
        """Fetch comments via API."""
        comments = []
        max_id = 0
        count = min(max_comments, 50)

        try:
            while len(comments) < max_comments:
                params = {
                    "id": mid,
                    "uid": uid,
                    "count": count,
                    "fetch_level": 0,
                }
                if max_id:
                    params["max_id"] = max_id

                response = await client.get(
                    f"{self.BASE_URL}{self.COMMENTS_API}",
                    params=params,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    break

                data = response.json()
                items = data.get("data", [])

                if not items:
                    break

                for item in items:
                    if len(comments) >= max_comments:
                        break

                    user_data = item.get("user", {})
                    comments.append(WeiboComment(
                        comment_id=str(item.get("id", "")),
                        user=WeiboUser(
                            id=str(user_data.get("id", "")),
                            screen_name=user_data.get("screen_name", ""),
                        ),
                        text=item.get("text_raw", item.get("text", "")),
                        created_at=item.get("created_at", ""),
                        likes=item.get("like_counts", 0),
                    ))

                max_id = data.get("max_id", 0)
                if not max_id:
                    break

                await asyncio.sleep(1)  # Rate limit

        except Exception as e:
            console.print(f"[dim]Warning fetching comments: {e}[/dim]")

        return comments

    async def _download_images(
        self, urls: List[str], output_dir: Path, client: httpx.AsyncClient
    ):
        """Download images to directory, named by content hash."""
        for url in urls:
            try:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    ext = ".jpg"
                    content_type = response.headers.get("content-type", "")
                    if "png" in content_type:
                        ext = ".png"
                    elif "gif" in content_type:
                        ext = ".gif"
                    elif "webp" in content_type:
                        ext = ".webp"

                    name = hashlib.md5(response.content).hexdigest()
                    path = output_dir / f"{name}{ext}"
                    path.write_bytes(response.content)
            except Exception:
                continue


def _parse_cookies(raw: str) -> list:
    """Parse cookies from multiple formats.

    Supports:
    - JSON array: [{"name": "x", "value": "y"}, ...]
    - Playwright storage_state: {"cookies": [...]}
    - Raw cookie string: "name1=val1; name2=val2"
    - Netscape HTTP Cookie File (tab-separated, exported by browser plugins)
    """
    raw = raw.strip()
    if not raw:
        return []

    # Try JSON first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "cookies" in parsed:
            return parsed["cookies"]
    except (json.JSONDecodeError, ValueError):
        pass

    # Try Netscape HTTP Cookie File format
    # Lines: domain \t flag \t path \t secure \t expiry \t name \t value
    lines = raw.splitlines()
    if any(line.startswith("# Netscape HTTP Cookie File") or
           line.startswith("# HTTP Cookie File") for line in lines[:5]):
        cookies = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append({"name": parts[5], "value": parts[6]})
        if cookies:
            return cookies

    # Also try tab-separated lines even without the header comment
    if "\t" in raw:
        cookies = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append({"name": parts[5], "value": parts[6]})
        if cookies:
            return cookies

    # Try raw cookie string: "name1=val1; name2=val2"
    if "=" in raw:
        cookies = []
        for pair in raw.replace("\n", ";").split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies.append({"name": name.strip(), "value": value.strip()})
        if cookies:
            return cookies

    return []
