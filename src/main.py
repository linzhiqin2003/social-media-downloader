"""Social Media Downloader - CLI entry point."""

import asyncio
import re
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:
    from .xiaohongshu import XiaohongshuDownloader
    from .weibo import WeiboDownloader
except ImportError:
    from src.xiaohongshu import XiaohongshuDownloader
    from src.weibo import WeiboDownloader

app = typer.Typer(
    name="smd",
    help="Social Media Downloader - Download content from Xiaohongshu and Weibo",
    no_args_is_help=False,  # Allow running without args to show interactive UI
    invoke_without_command=True,
)

console = Console()


@app.callback()
def main_callback(ctx: typer.Context):
    """Social Media Downloader - 小红书 & 微博内容下载器"""
    # If no command is provided, run interactive mode
    if ctx.invoked_subcommand is None:
        try:
            from .app import main as interactive_main
        except ImportError:
            from src.app import main as interactive_main
        interactive_main()
        raise typer.Exit()


def detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL."""
    url_lower = url.lower()
    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xiaohongshu"
    elif "weibo.com" in url_lower or "weibo.cn" in url_lower:
        return "weibo"
    return None


@app.command()
def download(
    urls: List[str] = typer.Argument(..., help="URLs to download (Xiaohongshu or Weibo)"),
    output: Path = typer.Option(Path("./downloads"), "-o", "--output", help="Output directory"),
    comments: bool = typer.Option(True, "--comments", is_flag=True, flag_value=True, help="Fetch comments (default: True)"),
    no_comments: bool = typer.Option(False, "--no-comments", is_flag=True, help="Skip comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Max comments per post"),
    images: bool = typer.Option(True, "--images", is_flag=True, flag_value=True, help="Download images (default: True)"),
    no_images: bool = typer.Option(False, "--no-images", is_flag=True, help="Skip images"),
) -> None:
    """Download content from URLs.

    Automatically detects platform (Xiaohongshu or Weibo) from URL.

    Examples:
        smd download "https://www.xiaohongshu.com/explore/xxx"
        smd download "https://weibo.com/1234/AbCdEf" -o ./my_downloads
        smd download URL1 URL2 URL3 --no-comments
    """
    # Handle flags
    fetch_comments = not no_comments
    download_images = not no_images

    # Group URLs by platform
    xhs_urls = []
    weibo_urls = []
    unknown_urls = []

    for url in urls:
        platform = detect_platform(url)
        if platform == "xiaohongshu":
            xhs_urls.append(url)
        elif platform == "weibo":
            weibo_urls.append(url)
        else:
            unknown_urls.append(url)

    if unknown_urls:
        console.print(f"[yellow]Unknown platform for: {', '.join(unknown_urls)}[/yellow]")

    async def _download():
        results = {"success": 0, "failed": 0}

        # Download Xiaohongshu
        if xhs_urls:
            console.print(f"\n[cyan]Downloading {len(xhs_urls)} Xiaohongshu note(s)...[/cyan]")
            async with XiaohongshuDownloader() as downloader:
                # Check login
                if not await downloader.check_login():
                    console.print("[yellow]Xiaohongshu not logged in. Initiating login...[/yellow]")
                    await downloader.login()

                xhs_output = output / "xiaohongshu"
                for url in xhs_urls:
                    result = await downloader.download(
                        url=url,
                        output_dir=xhs_output,
                        fetch_comments=fetch_comments,
                        max_comments=max_comments,
                        download_images=download_images,
                    )
                    if result:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

        # Download Weibo
        if weibo_urls:
            console.print(f"\n[cyan]Downloading {len(weibo_urls)} Weibo post(s)...[/cyan]")
            async with WeiboDownloader() as downloader:
                # Check login
                if not await downloader.check_login():
                    console.print("[yellow]Weibo not logged in. Initiating login...[/yellow]")
                    await downloader.login()

                weibo_output = output / "weibo"
                for url in weibo_urls:
                    result = await downloader.download(
                        url=url,
                        output_dir=weibo_output,
                        fetch_comments=fetch_comments,
                        max_comments=max_comments,
                        download_images=download_images,
                    )
                    if result:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

        # Summary
        console.print()
        console.print(Panel(
            f"[green]Success: {results['success']}[/green] | [red]Failed: {results['failed']}[/red]",
            title="Download Complete",
        ))

    asyncio.run(_download())


@app.command()
def login(
    platform: str = typer.Argument(..., help="Platform to login: 'xhs' or 'weibo'"),
) -> None:
    """Login to a platform.

    Examples:
        smd login xhs
        smd login weibo
    """
    async def _login():
        if platform.lower() in ("xhs", "xiaohongshu"):
            async with XiaohongshuDownloader() as downloader:
                await downloader.login()
        elif platform.lower() == "weibo":
            async with WeiboDownloader() as downloader:
                await downloader.login()
        else:
            console.print(f"[red]Unknown platform: {platform}[/red]")
            console.print("[dim]Use 'xhs' for Xiaohongshu or 'weibo' for Weibo[/dim]")

    asyncio.run(_login())


@app.command()
def status() -> None:
    """Check login status for all platforms."""
    async def _check():
        table = Table(title="Login Status")
        table.add_column("Platform", style="cyan")
        table.add_column("Status")

        # Check Xiaohongshu
        async with XiaohongshuDownloader() as xhs:
            xhs_status = await xhs.check_login()
            table.add_row(
                "Xiaohongshu",
                "[green]Logged in[/green]" if xhs_status else "[red]Not logged in[/red]"
            )

        # Check Weibo
        async with WeiboDownloader() as weibo:
            weibo_status = await weibo.check_login()
            table.add_row(
                "Weibo",
                "[green]Logged in[/green]" if weibo_status else "[red]Not logged in[/red]"
            )

        console.print(table)

    asyncio.run(_check())


@app.command()
def batch(
    file: Path = typer.Argument(..., help="File containing URLs (one per line)"),
    output: Path = typer.Option(Path("./downloads"), "-o", "--output", help="Output directory"),
    no_comments: bool = typer.Option(False, "--no-comments", is_flag=True, help="Skip comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Max comments per post"),
    no_images: bool = typer.Option(False, "--no-images", is_flag=True, help="Skip images"),
    delay: float = typer.Option(3.0, "--delay", help="Delay between downloads (seconds)"),
) -> None:
    """Batch download from a file containing URLs.

    Examples:
        smd batch urls.txt
        smd batch urls.txt -o ./my_downloads --delay 5
    """
    # Handle flags
    fetch_comments = not no_comments
    download_images = not no_images

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    urls = []
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    if not urls:
        console.print("[yellow]No URLs found in file.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[cyan]Found {len(urls)} URLs to download[/cyan]")

    async def _batch_download():
        results = {"success": 0, "failed": 0}

        # Group by platform
        xhs_urls = [u for u in urls if detect_platform(u) == "xiaohongshu"]
        weibo_urls = [u for u in urls if detect_platform(u) == "weibo"]

        # Download Xiaohongshu
        if xhs_urls:
            console.print(f"\n[cyan]Downloading {len(xhs_urls)} Xiaohongshu note(s)...[/cyan]")
            async with XiaohongshuDownloader() as downloader:
                if not await downloader.check_login():
                    console.print("[yellow]Xiaohongshu not logged in. Initiating login...[/yellow]")
                    await downloader.login()

                xhs_output = output / "xiaohongshu"
                for i, url in enumerate(xhs_urls):
                    console.print(f"\n[dim]({i+1}/{len(xhs_urls)})[/dim]")
                    result = await downloader.download(
                        url=url,
                        output_dir=xhs_output,
                        fetch_comments=fetch_comments,
                        max_comments=max_comments,
                        download_images=download_images,
                    )
                    if result:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

                    if i < len(xhs_urls) - 1:
                        await asyncio.sleep(delay)

        # Download Weibo
        if weibo_urls:
            console.print(f"\n[cyan]Downloading {len(weibo_urls)} Weibo post(s)...[/cyan]")
            async with WeiboDownloader() as downloader:
                if not await downloader.check_login():
                    console.print("[yellow]Weibo not logged in. Initiating login...[/yellow]")
                    await downloader.login()

                weibo_output = output / "weibo"
                for i, url in enumerate(weibo_urls):
                    console.print(f"\n[dim]({i+1}/{len(weibo_urls)})[/dim]")
                    result = await downloader.download(
                        url=url,
                        output_dir=weibo_output,
                        fetch_comments=fetch_comments,
                        max_comments=max_comments,
                        download_images=download_images,
                    )
                    if result:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

                    if i < len(weibo_urls) - 1:
                        await asyncio.sleep(delay)

        # Summary
        console.print()
        console.print(Panel(
            f"[green]Success: {results['success']}[/green] | [red]Failed: {results['failed']}[/red]",
            title="Batch Download Complete",
        ))

    asyncio.run(_batch_download())


if __name__ == "__main__":
    app()
