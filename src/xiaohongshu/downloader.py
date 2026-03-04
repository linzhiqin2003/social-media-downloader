"""Xiaohongshu content downloader."""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import async_playwright, Page, Browser
from pydantic import BaseModel, Field
from rich.console import Console

console = Console()


# ============ Data Models ============

class Author(BaseModel):
    """Author information."""
    user_id: str = ""
    nickname: str = ""
    avatar: str = ""


class Comment(BaseModel):
    """Comment information."""
    comment_id: str = ""
    content: str = ""
    author: Author = Field(default_factory=Author)
    likes: int = 0
    create_time: Optional[datetime] = None
    sub_comments: List["Comment"] = Field(default_factory=list)


class Note(BaseModel):
    """Full note information."""
    note_id: str
    title: str = ""
    content: str = ""
    images: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    publish_time: Optional[datetime] = None
    author: Author = Field(default_factory=Author)
    likes: int = 0
    comments_count: int = 0
    collects: int = 0
    shares: int = 0
    comments: List[Comment] = Field(default_factory=list)


# ============ Selectors ============

class Selectors:
    """CSS selectors for Xiaohongshu."""
    NOTE_TITLE = '#detail-title, .note-content .title'
    NOTE_CONTENT = '#detail-desc .note-text, .note-text, .desc'
    NOTE_IMAGES = '[class*="swiper"] img, [class*="carousel"] img, [class*="slide"] img'
    NOTE_VIDEO = 'video source, video'
    NOTE_TAGS = 'a.tag, a[id="hash-tag"], a[href*="/search_result?keyword"]'
    NOTE_TIME = '[class*="time"], [class*="date"]'
    NOTE_ERROR = 'text=当前笔记暂时无法浏览'
    AUTHOR_CONTAINER = '.author-container, .author-wrapper'
    AUTHOR_LINK = 'a[href*="/user/profile/"]'
    COMMENTS_CONTAINER = '#noteContainer .comments-container, .comments-container, .comment-list'
    COMMENT_ITEM = '.comment-inner, .comment-item, [class*="commentItem"]'
    COMMENT_CONTENT = '.content, .comment-content'
    COMMENT_AUTHOR_NAME = '.name, .author-name, .nickname'
    COMMENT_LIKES = '.like-count, .likes, [class*="like"] .count'
    COMMENT_TIME = '.time, .date, [class*="time"]'


# ============ Downloader ============

class XiaohongshuDownloader:
    """Download content from Xiaohongshu."""

    BASE_URL = "https://www.xiaohongshu.com"
    EXPLORE_URL = f"{BASE_URL}/explore"
    DATA_DIR = Path.home() / ".social_media_downloader" / "xiaohongshu"

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cookie_path = self.DATA_DIR / "cookies.json"
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

    def _get_storage_state(self) -> Optional[dict]:
        """Load storage state from file."""
        if self.cookie_path.exists():
            return str(self.cookie_path)
        return None

    async def login(self) -> bool:
        """Interactive login via QR code."""
        console.print("[cyan]Opening browser for login...[/cyan]")
        console.print("[yellow]Please scan QR code to login, then press Enter when done.[/yellow]")

        context = await self.browser.new_context()
        page = await context.new_page()

        await page.goto(self.BASE_URL)
        await asyncio.sleep(2)

        # Wait for user to login
        input("Press Enter after you've logged in...")

        # Save cookies
        storage = await context.storage_state()
        with open(self.cookie_path, "w") as f:
            json.dump(storage, f)

        await context.close()
        console.print("[green]Login successful! Cookies saved.[/green]")
        return True

    async def check_login(self) -> bool:
        """Check if logged in."""
        if not self.cookie_path.exists():
            return False

        context = await self.browser.new_context(storage_state=str(self.cookie_path))
        page = await context.new_page()

        try:
            await page.goto(self.BASE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Check for login button
            login_btn = await page.query_selector('button:has-text("登录")')
            is_logged_in = login_btn is None

            await context.close()
            return is_logged_in
        except Exception:
            await context.close()
            return False

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        """Parse note ID and xsec_token from URL."""
        if not url.startswith("http"):
            return url.strip(), ""

        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        note_id = ""
        for i, part in enumerate(path_parts):
            if part in ("explore", "discovery", "item", "search_result") and i + 1 < len(path_parts):
                note_id = path_parts[i + 1]
                break

        if not note_id and path_parts:
            note_id = path_parts[-1]

        params = parse_qs(parsed.query)
        xsec_token = params.get("xsec_token", [""])[0]

        return note_id, xsec_token

    async def download(
        self,
        url: str,
        output_dir: Path,
        fetch_comments: bool = True,
        max_comments: int = 50,
        download_images: bool = True,
    ) -> Optional[Note]:
        """Download a note by URL.

        Args:
            url: Note URL or ID.
            output_dir: Directory to save content.
            fetch_comments: Whether to fetch comments.
            max_comments: Maximum comments to fetch.
            download_images: Whether to download images.

        Returns:
            Note object with content.
        """
        note_id, xsec_token = self.parse_url(url)
        if not note_id:
            console.print(f"[red]Invalid URL: {url}[/red]")
            return None

        storage_state = self._get_storage_state()
        if not storage_state:
            console.print("[yellow]Not logged in. Please login first.[/yellow]")
            return None

        context = await self.browser.new_context(storage_state=storage_state)
        page = await context.new_page()

        try:
            note_url = f"{self.EXPLORE_URL}/{note_id}"
            if xsec_token:
                note_url = f"{note_url}?xsec_token={xsec_token}&xsec_source="

            console.print(f"[cyan]Fetching note: {note_id}[/cyan]")
            await page.goto(note_url, wait_until="commit", timeout=60000)
            await asyncio.sleep(3)

            # Check for error
            error_msg = await page.query_selector(Selectors.NOTE_ERROR)
            if error_msg:
                console.print("[red]Note is not accessible.[/red]")
                return None

            # Extract note details
            note = await self._extract_note(page, note_id)
            if not note:
                return None

            # Fetch comments
            if fetch_comments:
                note.comments = await self._extract_comments(page, max_comments)

            # Download images
            if download_images and note.images:
                note_dir = output_dir / note_id
                note_dir.mkdir(parents=True, exist_ok=True)
                await self._download_images(note.images, note_dir)
                console.print(f"[green]Downloaded {len(note.images)} images to {note_dir}[/green]")

            # Save JSON
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / f"{note_id}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(note.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            console.print(f"[green]Saved content to {json_path}[/green]")

            return note

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return None
        finally:
            await context.close()

    async def _extract_note(self, page: Page, note_id: str) -> Optional[Note]:
        """Extract note details from page."""
        try:
            await page.wait_for_selector('.note-content, #detail-title', timeout=10000)

            # Title
            title = ""
            title_el = await page.query_selector(Selectors.NOTE_TITLE)
            if title_el:
                title = (await title_el.text_content() or "").strip()

            # Content
            content = ""
            content_el = await page.query_selector(Selectors.NOTE_CONTENT)
            if content_el:
                content = (await content_el.text_content() or "").strip()

            # Images
            images: List[str] = []
            img_elements = await page.query_selector_all(Selectors.NOTE_IMAGES)
            for img in img_elements:
                src = await img.get_attribute("src")
                if src and "http" in src:
                    images.append(src)

            # Video
            video_url = None
            video_el = await page.query_selector(Selectors.NOTE_VIDEO)
            if video_el:
                video_url = await video_el.get_attribute("src")

            # Tags
            tags: List[str] = []
            tag_elements = await page.query_selector_all(Selectors.NOTE_TAGS)
            for tag_el in tag_elements:
                tag_text = await tag_el.text_content()
                if tag_text:
                    tag_text = tag_text.strip().replace("#", "")
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)

            # Time
            publish_time = None
            time_el = await page.query_selector(Selectors.NOTE_TIME)
            if time_el:
                time_text = await time_el.text_content() or ""
                publish_time = self._parse_time(time_text)

            # Author
            author = await self._extract_author(page)

            # Stats
            likes = await self._extract_stat(page, "like")
            comments_count = await self._extract_stat(page, "comment")
            collects = await self._extract_stat(page, "collect")
            shares = await self._extract_stat(page, "share")

            return Note(
                note_id=note_id,
                title=title,
                content=content,
                images=images,
                video_url=video_url,
                tags=tags,
                publish_time=publish_time,
                author=author,
                likes=likes,
                comments_count=comments_count,
                collects=collects,
                shares=shares,
            )

        except Exception as e:
            console.print(f"[red]Error extracting note: {e}[/red]")
            return None

    async def _extract_author(self, page: Page) -> Author:
        """Extract author info."""
        try:
            container = await page.query_selector(Selectors.AUTHOR_CONTAINER)
            if not container:
                return Author()

            link = await container.query_selector(Selectors.AUTHOR_LINK)
            user_id = ""
            if link:
                href = await link.get_attribute("href") or ""
                parts = href.strip("/").split("/")
                if len(parts) >= 3 and parts[0] == "user" and parts[1] == "profile":
                    user_id = parts[2]

            nickname = ""
            name_el = await container.query_selector('.name, .username')
            if name_el:
                nickname = (await name_el.text_content() or "").strip()

            avatar = ""
            avatar_el = await container.query_selector('img.avatar-item, .avatar img, img')
            if avatar_el:
                avatar = await avatar_el.get_attribute("src") or ""

            return Author(user_id=user_id, nickname=nickname, avatar=avatar)
        except Exception:
            return Author()

    async def _extract_stat(self, page: Page, stat_type: str) -> int:
        """Extract engagement stat."""
        try:
            el = await page.query_selector(f'[class*="{stat_type}"] [class*="count"], [class*="{stat_type}"] span')
            if el:
                text = await el.text_content() or "0"
                return self._parse_count(text)
            return 0
        except Exception:
            return 0

    async def _extract_comments(self, page: Page, max_comments: int) -> List[Comment]:
        """Extract comments from page."""
        comments: List[Comment] = []

        try:
            # Scroll to comments
            section = await page.query_selector(Selectors.COMMENTS_CONTAINER)
            if section:
                await section.scroll_into_view_if_needed()
                await asyncio.sleep(2)

            # Extract comment items
            items = await page.query_selector_all(Selectors.COMMENT_ITEM)

            for item in items[:max_comments]:
                try:
                    # Content
                    content = ""
                    content_el = await item.query_selector(Selectors.COMMENT_CONTENT)
                    if content_el:
                        content = (await content_el.text_content() or "").strip()

                    if not content:
                        continue

                    # Author
                    author_name = ""
                    name_el = await item.query_selector(Selectors.COMMENT_AUTHOR_NAME)
                    if name_el:
                        author_name = (await name_el.text_content() or "").strip()

                    # Likes
                    likes = 0
                    likes_el = await item.query_selector(Selectors.COMMENT_LIKES)
                    if likes_el:
                        likes_text = await likes_el.text_content() or "0"
                        likes = self._parse_count(likes_text)

                    # Time
                    create_time = None
                    time_el = await item.query_selector(Selectors.COMMENT_TIME)
                    if time_el:
                        time_text = await time_el.text_content() or ""
                        create_time = self._parse_time(time_text)

                    comments.append(Comment(
                        comment_id=str(hash(content))[:12],
                        content=content,
                        author=Author(nickname=author_name),
                        likes=likes,
                        create_time=create_time,
                    ))

                except Exception:
                    continue

        except Exception as e:
            console.print(f"[dim]Warning extracting comments: {e}[/dim]")

        return comments

    async def _download_images(self, urls: List[str], output_dir: Path):
        """Download images to directory."""
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            for i, url in enumerate(urls):
                try:
                    ext = ".jpg"
                    if "png" in url.lower():
                        ext = ".png"
                    elif "webp" in url.lower():
                        ext = ".webp"

                    response = await client.get(url, timeout=30.0)
                    if response.status_code == 200:
                        path = output_dir / f"image_{i+1:02d}{ext}"
                        path.write_bytes(response.content)
                except Exception:
                    continue

    @staticmethod
    def _parse_count(text: str) -> int:
        """Parse count like '1.2万' or '1234'."""
        text = text.strip()
        try:
            if "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            elif "亿" in text:
                return int(float(text.replace("亿", "")) * 100000000)
            else:
                clean = "".join(c for c in text if c.isdigit() or c == ".")
                return int(float(clean)) if clean else 0
        except Exception:
            return 0

    @staticmethod
    def _parse_time(text: str) -> Optional[datetime]:
        """Parse time from various formats."""
        text = text.strip()

        patterns = [
            r"(\d{4})-(\d{2})-(\d{2})",
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                try:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    return datetime(year, month, day)
                except Exception:
                    continue

        if "刚刚" in text or "秒前" in text:
            return datetime.now()
        elif "分钟前" in text:
            match = re.search(r"(\d+)分钟前", text)
            if match:
                return datetime.now() - timedelta(minutes=int(match.group(1)))
        elif "小时前" in text:
            match = re.search(r"(\d+)小时前", text)
            if match:
                return datetime.now() - timedelta(hours=int(match.group(1)))
        elif "天前" in text:
            match = re.search(r"(\d+)天前", text)
            if match:
                return datetime.now() - timedelta(days=int(match.group(1)))

        return None
