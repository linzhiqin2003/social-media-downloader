"""Xiaohongshu downloader — pure HTTP, no browser dependency.

- Note data: HTTP GET + parse __INITIAL_STATE__ from SSR HTML
- Images: direct CDN download
- Comments: not supported (requires browser signing)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field
from rich.console import Console

console = Console()


# ============ Data Models ============

class Author(BaseModel):
    user_id: str = ""
    nickname: str = ""
    avatar: str = ""


class Note(BaseModel):
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
    ip_location: str = ""
    note_type: str = "normal"


# ============ Downloader ============

class XiaohongshuDownloader:
    """Pure HTTP downloader for Xiaohongshu (no Playwright)."""

    BASE_URL = "https://www.xiaohongshu.com"
    EXPLORE_URL = f"{BASE_URL}/explore"
    DATA_DIR = Path.home() / ".social_media_downloader" / "xiaohongshu"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.xiaohongshu.com/",
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
                return {c["name"]: c["value"] for c in data["cookies"]}

            # Plain cookie list [{name, value, ...}, ...]
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data}

            return {}
        except Exception:
            return {}

    async def check_login(self) -> bool:
        """Check if cookies exist and contain essential keys."""
        cookies = self._load_cookies()
        return "web_session" in cookies or "a1" in cookies

    async def login(self) -> bool:
        """Guide user to import cookies from browser."""
        console.print()
        console.print("[bold cyan]小红书 Cookie 导入指南[/bold cyan]")
        console.print()
        console.print("1. 在浏览器中打开 [link=https://www.xiaohongshu.com]xiaohongshu.com[/link] 并登录")
        console.print("2. 按 F12 打开开发者工具 → 控制台 (Console)")
        console.print("3. 粘贴以下代码并回车：")
        console.print()
        console.print(
            "[dim]copy(document.cookie.split('; ')"
            ".map(c => { const [n,...v] = c.split('='); "
            "return {name:n, value:v.join('=')} }))[/dim]"
        )
        console.print()
        console.print("4. 已复制到剪贴板，粘贴到下面：")
        console.print()

        raw = input("粘贴 Cookie JSON > ").strip()
        if not raw:
            console.print("[red]未输入内容[/red]")
            return False

        try:
            cookies = json.loads(raw)
            if not isinstance(cookies, list):
                raise ValueError("not a list")

            # Save
            with open(self.cookie_path, "w") as f:
                json.dump(cookies, f, ensure_ascii=False)

            names = {c["name"] for c in cookies}
            if "web_session" in names or "a1" in names:
                console.print("[green]Cookie 导入成功！[/green]")
                return True
            else:
                console.print("[yellow]Cookie 已保存，但缺少关键 cookie (web_session/a1)[/yellow]")
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
        return "web_session" in names or "a1" in names

    # ---- URL parsing ----

    @staticmethod
    def parse_url(url: str) -> Tuple[str, str]:
        """Parse note_id and xsec_token from URL."""
        note_id = ""
        xsec_token = ""

        for pattern in [
            r'/explore/([a-zA-Z0-9]+)',
            r'/discovery/item/([a-zA-Z0-9]+)',
            r'/note/([a-zA-Z0-9]+)',
        ]:
            m = re.search(pattern, url)
            if m:
                note_id = m.group(1)
                break

        if not note_id:
            clean = url.strip().split('?')[0].split('/')[-1]
            if re.match(r'^[a-zA-Z0-9]+$', clean):
                note_id = clean

        m = re.search(r'xsec_token=([^&]+)', url)
        if m:
            xsec_token = m.group(1)

        return note_id, xsec_token

    # ---- Download ----

    async def download(
        self,
        url: str,
        output_dir: Path,
        fetch_comments: bool = True,
        max_comments: int = 50,
        download_images: bool = True,
    ) -> Optional[Note]:
        """Download a note by URL (pure HTTP)."""
        note_id, xsec_token = self.parse_url(url)
        if not note_id:
            console.print(f"[red]Invalid URL: {url}[/red]")
            return None

        cookies = self._load_cookies()
        if not cookies:
            console.print("[yellow]未登录，请先导入 Cookie[/yellow]")
            return None

        page_url = f"{self.EXPLORE_URL}/{note_id}"
        if xsec_token:
            page_url += f"?xsec_token={xsec_token}&xsec_source="

        console.print(f"[cyan]Fetching note: {note_id}[/cyan]")

        async with httpx.AsyncClient(
            cookies=cookies,
            headers=self.HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                resp = await client.get(page_url)
            except Exception as e:
                console.print(f"[red]HTTP error: {e}[/red]")
                return None

            if resp.status_code != 200:
                console.print(f"[red]HTTP {resp.status_code}[/red]")
                return None

            # Extract __INITIAL_STATE__ from HTML
            note = self._extract_from_html(resp.text, note_id)
            if not note:
                if "验证" in resp.text or "/404" in str(resp.url):
                    console.print("[yellow]需要验证码或页面不可访问，xsec_token 可能已过期[/yellow]")
                else:
                    console.print("[yellow]SSR 数据提取失败[/yellow]")
                return None

            title_preview = (note.title[:30] + "...") if len(note.title) > 30 else note.title
            console.print(f"[green]Fetched: {title_preview} ({len(note.images)} images)[/green]")

            # Download images
            if download_images and note.images:
                note_dir = output_dir / note_id
                note_dir.mkdir(parents=True, exist_ok=True)
                await self._download_images(note.images, note_dir, client)
                console.print(f"[green]Downloaded {len(note.images)} images → {note_dir}[/green]")

            # Save JSON
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / f"{note_id}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(note.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            console.print(f"[green]Saved → {json_path}[/green]")

            return note

    # ---- SSR extraction ----

    def _extract_from_html(self, html: str, note_id: str) -> Optional[Note]:
        """Extract note from __INITIAL_STATE__ in HTML."""
        try:
            match = re.search(
                r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>',
                html, re.DOTALL,
            )
            if not match:
                return None

            raw = match.group(1)
            # XHS puts literal `undefined` in JSON
            raw = raw.replace('undefined', 'null')
            state = json.loads(raw)

            note_map = state.get("note", {}).get("noteDetailMap", {})
            nd = note_map.get(note_id)
            if not nd or not nd.get("note"):
                return None

            n = nd["note"]

            # Images
            images = []
            for img in n.get("imageList", []):
                url = img.get("urlDefault", "")
                if not url:
                    for info in img.get("infoList", []):
                        if info.get("imageScene") == "WB_DFT":
                            url = info.get("url", "")
                            break
                if not url:
                    for info in img.get("infoList", []):
                        url = info.get("url", "")
                        if url:
                            break
                if url:
                    images.append(url)

            # Video
            video_url = None
            if n.get("video"):
                video_url = (
                    n["video"].get("media", {}).get("stream", {})
                    .get("h264", [{}])[0].get("masterUrl", "")
                ) or None

            # Stats
            interact = n.get("interactInfo") or {}
            likes = _parse_count(str(interact.get("likedCount", "0")))
            collects = _parse_count(str(interact.get("collectedCount", "0")))
            comments_count = _parse_count(str(interact.get("commentCount", "0")))
            shares = _parse_count(str(interact.get("shareCount", "0")))

            # Time
            publish_time = None
            ts = n.get("time")
            if ts:
                try:
                    publish_time = datetime.fromtimestamp(ts / 1000)
                except (ValueError, OSError):
                    pass

            # Author
            u = n.get("user") or {}
            author = Author(
                user_id=u.get("userId", ""),
                nickname=u.get("nickname", ""),
                avatar=u.get("avatar", ""),
            )

            # Tags
            tags = [t["name"] for t in n.get("tagList", []) if t.get("name")]

            return Note(
                note_id=n.get("noteId", note_id),
                title=n.get("title", ""),
                content=n.get("desc", ""),
                images=images,
                video_url=video_url,
                tags=tags,
                publish_time=publish_time,
                author=author,
                likes=likes,
                comments_count=comments_count,
                collects=collects,
                shares=shares,
                ip_location=n.get("ipLocation", ""),
                note_type=n.get("type", "normal"),
            )

        except Exception as e:
            console.print(f"[dim]SSR extraction error: {e}[/dim]")
            return None

    # ---- Image download ----

    async def _download_images(
        self, urls: List[str], output_dir: Path, client: httpx.AsyncClient
    ):
        """Download images to directory."""
        for i, url in enumerate(urls):
            try:
                ext = ".jpg"
                if "png" in url.lower():
                    ext = ".png"
                elif "webp" in url.lower():
                    ext = ".webp"

                resp = await client.get(url, timeout=30.0)
                if resp.status_code == 200:
                    path = output_dir / f"image_{i+1:02d}{ext}"
                    path.write_bytes(resp.content)
            except Exception:
                continue


# ---- Helpers ----

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


def _parse_count(text: str) -> int:
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
