"""Xiaohongshu API-based content downloader.

Uses Playwright as a signing oracle:
- Note detail: extracted from SSR __INITIAL_STATE__ (no API signing needed)
- Comments: fetched via /api/sns/web/v2/comment/page through browser's network stack
- Images: direct CDN download (no auth needed)
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

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
    ip_location: str = ""


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
    ip_location: str = ""
    note_type: str = "normal"


# ============ Downloader ============

class XiaohongshuDownloader:
    """API-based downloader for Xiaohongshu."""

    BASE_URL = "https://www.xiaohongshu.com"
    EXPLORE_URL = f"{BASE_URL}/explore"
    DATA_DIR = Path.home() / ".social_media_downloader" / "xiaohongshu"

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cookie_path = self.DATA_DIR / "cookies.json"
        self.browser: Optional[Browser] = None
        self.playwright = None
        self._session_warm = False  # Track if session is warmed up

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
        """Load storage state (Playwright format) from file.

        Handles two cookie formats:
        - Playwright storage_state: {"cookies": [...], "origins": [...]}
        - Plain cookie list: [{name, value, domain, ...}, ...]
        """
        if not self.cookie_path.exists():
            return None

        try:
            with open(self.cookie_path, "r") as f:
                data = json.load(f)

            # Already in storage_state format
            if isinstance(data, dict) and "cookies" in data:
                return data

            # Plain cookie list — wrap into storage_state format
            if isinstance(data, list):
                return {"cookies": data, "origins": []}

            return None
        except Exception:
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
        """Check if logged in (lightweight: just check cookie file)."""
        state = self._get_storage_state()
        if not state:
            return False

        try:
            cookies = state.get("cookies", [])
            cookie_names = {c.get("name", "") for c in cookies}
            return "web_session" in cookie_names or "a1" in cookie_names
        except Exception:
            return False

    @staticmethod
    def parse_url(url: str) -> Tuple[str, str]:
        """Parse note_id and xsec_token from a XHS URL.

        Supports formats:
        - https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...
        - https://www.xiaohongshu.com/discovery/item/{note_id}?...
        - https://xhslink.com/xxx (short link)
        - Just a note_id string
        """
        note_id = ""
        xsec_token = ""

        # Extract note_id
        patterns = [
            r'/explore/([a-zA-Z0-9]+)',
            r'/discovery/item/([a-zA-Z0-9]+)',
            r'/note/([a-zA-Z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                note_id = match.group(1)
                break

        if not note_id:
            clean = url.strip().split('?')[0].split('/')[-1]
            if re.match(r'^[a-zA-Z0-9]+$', clean):
                note_id = clean

        # Extract xsec_token
        token_match = re.search(r'xsec_token=([^&]+)', url)
        if token_match:
            xsec_token = token_match.group(1)

        return note_id, xsec_token

    async def download(
        self,
        url: str,
        output_dir: Path,
        fetch_comments: bool = True,
        max_comments: int = 50,
        download_images: bool = True,
    ) -> Optional[Note]:
        """Download a note by URL using API extraction.

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

        state = self._get_storage_state()
        if not state:
            console.print("[yellow]Not logged in. Please login first.[/yellow]")
            return None

        context = await self.browser.new_context(storage_state=state)
        page = await context.new_page()

        try:
            page_url = f"{self.EXPLORE_URL}/{note_id}"
            if xsec_token:
                page_url += f"?xsec_token={xsec_token}&xsec_source="

            console.print(f"[cyan]Fetching note: {note_id}[/cyan]")

            # Navigate to note page
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass  # Timeout OK — page might be slow

            await asyncio.sleep(2)

            # Check if redirected (CAPTCHA or 404)
            current_url = page.url
            if "/404" in current_url or (
                f"/explore/{note_id}" not in current_url
                and note_id not in current_url
            ):
                console.print("[dim]Redirected, warming up session...[/dim]")

                # Warm up: go to explore page first
                if not await self._warm_up_session(page):
                    console.print("[yellow]Session warm-up failed[/yellow]")
                    await context.close()
                    return None

                # Retry navigation
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(2)

                if f"/explore/{note_id}" not in page.url and note_id not in page.url:
                    console.print(f"[yellow]Cannot access note {note_id}, token may be expired[/yellow]")
                    await context.close()
                    return None

            # Close login modal if present
            await self._close_login_modal(page)

            # Extract note from SSR state
            note = await self._extract_from_ssr(page, note_id)
            if not note:
                console.print("[yellow]SSR extraction failed, note may be inaccessible[/yellow]")
                await context.close()
                return None

            # Fetch comments via API
            if fetch_comments:
                comments = await self._fetch_comments_api(
                    page, note_id, xsec_token, max_comments
                )
                note.comments = comments
                note.comments_count = max(note.comments_count, len(comments))

            console.print(
                f"[green]Fetched: {note.title[:30]}{'...' if len(note.title) > 30 else ''} "
                f"({len(note.images)} images, {len(note.comments)} comments)[/green]"
            )

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

            await context.close()
            return note

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            await context.close()
            return None

    async def _warm_up_session(self, page: Page) -> bool:
        """Navigate to explore page to establish session and pass CAPTCHA."""
        try:
            console.print("[dim]Warming up session...[/dim]")
            try:
                await page.goto(self.EXPLORE_URL, wait_until="commit", timeout=60000)
            except Exception:
                pass

            # Wait for page to settle
            await asyncio.sleep(5)

            if "/explore" in page.url and "/404" not in page.url:
                return True

            # May be stuck on CAPTCHA — wait longer
            console.print("[yellow]Waiting for CAPTCHA resolution...[/yellow]")
            await asyncio.sleep(15)
            return "/explore" in page.url and "/404" not in page.url

        except Exception:
            return False

    async def _close_login_modal(self, page: Page):
        """Close the login popup if it appears."""
        try:
            close_btn = await page.query_selector('.close-button, [class*="close"], .login-close')
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _extract_from_ssr(self, page: Page, note_id: str) -> Optional[Note]:
        """Extract note data from __INITIAL_STATE__ SSR data."""
        try:
            data = await page.evaluate("""(noteId) => {
                const state = window.__INITIAL_STATE__;
                if (!state || !state.note || !state.note.noteDetailMap) return null;

                const noteData = state.note.noteDetailMap[noteId];
                if (!noteData || !noteData.note) return null;

                const n = noteData.note;
                return {
                    noteId: n.noteId,
                    title: n.title || '',
                    desc: n.desc || '',
                    type: n.type || 'normal',
                    time: n.time,
                    lastUpdateTime: n.lastUpdateTime,
                    ipLocation: n.ipLocation || '',
                    imageList: (n.imageList || []).map(img => ({
                        width: img.width,
                        height: img.height,
                        urlDefault: img.urlDefault || '',
                        urlPre: img.urlPre || '',
                        infoList: (img.infoList || []).map(info => ({
                            imageScene: info.imageScene,
                            url: info.url,
                        })),
                    })),
                    video: n.video ? {
                        url: n.video.media?.stream?.h264?.[0]?.masterUrl || '',
                        duration: n.video.duration || 0,
                    } : null,
                    tagList: (n.tagList || []).map(t => ({ id: t.id, name: t.name })),
                    user: n.user ? {
                        userId: n.user.userId || '',
                        nickname: n.user.nickname || '',
                        avatar: n.user.avatar || '',
                    } : null,
                    interactInfo: n.interactInfo ? {
                        likedCount: n.interactInfo.likedCount || '0',
                        collectedCount: n.interactInfo.collectedCount || '0',
                        commentCount: n.interactInfo.commentCount || '0',
                        shareCount: n.interactInfo.shareCount || '0',
                    } : null,
                };
            }""", note_id)

            if not data:
                return None

            # Build image URL list
            images = []
            for img in data.get("imageList", []):
                url = img.get("urlDefault", "")
                if not url:
                    for info in img.get("infoList", []):
                        if info.get("imageScene") == "WB_DFT":
                            url = info["url"]
                            break
                if not url:
                    for info in img.get("infoList", []):
                        url = info.get("url", "")
                        if url:
                            break
                if url:
                    images.append(url)

            # Video URL
            video_url = None
            if data.get("video"):
                video_url = data["video"].get("url")

            # Stats
            interact = data.get("interactInfo") or {}
            likes = self._parse_count(str(interact.get("likedCount", "0")))
            collects = self._parse_count(str(interact.get("collectedCount", "0")))
            comments_count = self._parse_count(str(interact.get("commentCount", "0")))
            shares = self._parse_count(str(interact.get("shareCount", "0")))

            # Time
            publish_time = None
            ts = data.get("time")
            if ts:
                try:
                    publish_time = datetime.fromtimestamp(ts / 1000)
                except (ValueError, OSError):
                    pass

            # Author
            user = data.get("user") or {}
            author = Author(
                user_id=user.get("userId", ""),
                nickname=user.get("nickname", ""),
                avatar=user.get("avatar", ""),
            )

            # Tags
            tags = [t["name"] for t in data.get("tagList", []) if t.get("name")]

            return Note(
                note_id=data.get("noteId", note_id),
                title=data.get("title", ""),
                content=data.get("desc", ""),
                images=images,
                video_url=video_url,
                tags=tags,
                publish_time=publish_time,
                author=author,
                likes=likes,
                comments_count=comments_count,
                collects=collects,
                shares=shares,
                ip_location=data.get("ipLocation", ""),
                note_type=data.get("type", "normal"),
            )

        except Exception as e:
            console.print(f"[dim]SSR extraction error: {e}[/dim]")
            return None

    async def _fetch_comments_api(
        self,
        page: Page,
        note_id: str,
        xsec_token: str,
        max_comments: int = 50,
    ) -> List[Comment]:
        """Fetch comments via browser API (service worker auto-signs)."""
        all_comments = []
        cursor = ""

        while len(all_comments) < max_comments:
            try:
                result = await page.evaluate("""async ({noteId, xsecToken, cursor}) => {
                    const params = new URLSearchParams({
                        note_id: noteId,
                        cursor: cursor,
                        top_comment_id: '',
                        image_formats: 'jpg,webp,avif',
                        xsec_token: xsecToken,
                    });
                    const url = `https://edith.xiaohongshu.com/api/sns/web/v2/comment/page?${params}`;

                    const resp = await fetch(url, {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Origin': 'https://www.xiaohongshu.com',
                            'Referer': 'https://www.xiaohongshu.com/',
                        },
                    });

                    const data = await resp.json();
                    if (!data.data) return { comments: [], hasMore: false, cursor: '' };

                    return {
                        comments: (data.data.comments || []).map(c => ({
                            id: c.id,
                            content: c.content,
                            likeCount: c.like_count || '0',
                            createTime: c.create_time,
                            ipLocation: c.ip_location || '',
                            user: c.user_info ? {
                                userId: c.user_info.user_id,
                                nickname: c.user_info.nickname,
                                avatar: c.user_info.image,
                            } : null,
                            subComments: (c.sub_comments || []).map(sc => ({
                                id: sc.id,
                                content: sc.content,
                                likeCount: sc.like_count || '0',
                                createTime: sc.create_time,
                                ipLocation: sc.ip_location || '',
                                user: sc.user_info ? {
                                    userId: sc.user_info.user_id,
                                    nickname: sc.user_info.nickname,
                                    avatar: sc.user_info.image,
                                } : null,
                            })),
                        })),
                        hasMore: data.data.has_more || false,
                        cursor: data.data.cursor || '',
                    };
                }""", {"noteId": note_id, "xsecToken": xsec_token, "cursor": cursor})

                if not result or not result.get("comments"):
                    break

                for c in result["comments"]:
                    comment = self._build_comment(c)
                    if comment:
                        all_comments.append(comment)

                if not result.get("hasMore"):
                    break

                cursor = result.get("cursor", "")
                if not cursor:
                    break

                await asyncio.sleep(0.5)

            except Exception as e:
                console.print(f"[dim]Comment fetch error: {e}[/dim]")
                break

        return all_comments[:max_comments]

    def _build_comment(self, data: dict) -> Optional[Comment]:
        """Build a Comment object from API response data."""
        if not data or not data.get("content"):
            return None

        user = data.get("user") or {}
        author = Author(
            user_id=user.get("userId", ""),
            nickname=user.get("nickname", ""),
            avatar=user.get("avatar", ""),
        )

        create_time = None
        ts = data.get("createTime")
        if ts:
            try:
                create_time = datetime.fromtimestamp(ts / 1000)
            except (ValueError, OSError):
                pass

        # Sub-comments
        sub_comments = []
        for sc in data.get("subComments", []):
            sub = self._build_comment(sc)
            if sub:
                sub_comments.append(sub)

        return Comment(
            comment_id=data.get("id", ""),
            content=data.get("content", ""),
            author=author,
            likes=self._parse_count(str(data.get("likeCount", "0"))),
            create_time=create_time,
            sub_comments=sub_comments,
            ip_location=data.get("ipLocation", ""),
        )

    async def _download_images(self, urls: List[str], output_dir: Path):
        """Download images to directory."""
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
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
