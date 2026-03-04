"""Weibo content downloader."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, Browser
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
    """Download content from Weibo."""

    BASE_URL = "https://weibo.com"
    MOBILE_URL = "https://m.weibo.cn"
    DATA_DIR = Path.home() / ".social_media_downloader" / "weibo"

    DETAIL_API = "/ajax/statuses/show"
    COMMENTS_API = "/ajax/statuses/buildComments"

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.DATA_DIR / "browser_state.json"
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def _get_storage_state(self) -> Optional[str]:
        """Load storage state path."""
        if self.storage_path.exists():
            return str(self.storage_path)
        return None

    def _get_cookies_for_httpx(self) -> dict:
        """Load cookies for httpx."""
        if not self.storage_path.exists():
            return {}

        with open(self.storage_path, "r") as f:
            state = json.load(f)

        cookies = {}
        for cookie in state.get("cookies", []):
            if "weibo" in cookie.get("domain", ""):
                cookies[cookie["name"]] = cookie["value"]
        return cookies

    async def login(self) -> bool:
        """Interactive login."""
        console.print("[cyan]Opening browser for login...[/cyan]")
        console.print("[yellow]Please login to Weibo, then press Enter when done.[/yellow]")

        context = await self.browser.new_context()
        page = await context.new_page()

        await page.goto(self.BASE_URL)
        await asyncio.sleep(2)

        input("Press Enter after you've logged in...")

        # Save storage state
        storage = await context.storage_state()
        with open(self.storage_path, "w") as f:
            json.dump(storage, f)

        await context.close()
        console.print("[green]Login successful! State saved.[/green]")
        return True

    async def check_login(self) -> bool:
        """Check if logged in."""
        if not self.storage_path.exists():
            return False

        cookies = self._get_cookies_for_httpx()
        if not cookies:
            return False

        # Try to access a protected endpoint
        try:
            async with httpx.AsyncClient(cookies=cookies) as client:
                response = await client.get(
                    f"{self.BASE_URL}/ajax/side/hotSearch",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                return response.status_code == 200
        except Exception:
            return False

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

    async def download(
        self,
        url: str,
        output_dir: Path,
        fetch_comments: bool = True,
        max_comments: int = 50,
        download_images: bool = True,
    ) -> Optional[WeiboPost]:
        """Download a post by URL.

        Args:
            url: Post URL or MID.
            output_dir: Directory to save content.
            fetch_comments: Whether to fetch comments.
            max_comments: Maximum comments to fetch.
            download_images: Whether to download images.

        Returns:
            WeiboPost object with content.
        """
        mid = self.parse_url(url)
        if not mid:
            console.print(f"[red]Invalid URL: {url}[/red]")
            return None

        cookies = self._get_cookies_for_httpx()
        if not cookies:
            console.print("[yellow]Not logged in. Please login first.[/yellow]")
            return None

        console.print(f"[cyan]Fetching post: {mid}[/cyan]")

        async with httpx.AsyncClient(
            cookies=cookies,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": self.BASE_URL,
            },
            follow_redirects=True,
        ) as client:

            # Fetch post details
            post = await self._fetch_post(client, mid)
            if not post:
                console.print("[red]Failed to fetch post.[/red]")
                return None

            # Fetch comments
            if fetch_comments and post.comments_count > 0:
                post.comments = await self._fetch_comments(client, mid, post.user.id, max_comments)
                console.print(f"[green]Fetched {len(post.comments)} comments[/green]")

            # Download images
            if download_images and post.images:
                post_dir = output_dir / mid
                post_dir.mkdir(parents=True, exist_ok=True)
                await self._download_images(post.images, post_dir, client)
                console.print(f"[green]Downloaded {len(post.images)} images to {post_dir}[/green]")

            # Save JSON
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / f"{mid}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(post.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            console.print(f"[green]Saved content to {json_path}[/green]")

            return post

    async def _fetch_post(self, client: httpx.AsyncClient, mid: str) -> Optional[WeiboPost]:
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
                # Prefer largest size
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
                video_url = media_info.get("stream_url_hd") or media_info.get("stream_url")

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

    async def _download_images(self, urls: List[str], output_dir: Path, client: httpx.AsyncClient):
        """Download images to directory."""
        for i, url in enumerate(urls):
            try:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    # Determine extension
                    ext = ".jpg"
                    content_type = response.headers.get("content-type", "")
                    if "png" in content_type:
                        ext = ".png"
                    elif "gif" in content_type:
                        ext = ".gif"
                    elif "webp" in content_type:
                        ext = ".webp"

                    path = output_dir / f"image_{i+1:02d}{ext}"
                    path.write_bytes(response.content)
            except Exception:
                continue
