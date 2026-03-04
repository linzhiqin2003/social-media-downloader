"""Interactive application for Social Media Downloader."""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.box import ROUNDED

try:
    from .ui import (
        clear_screen,
        print_banner,
        print_logo_small,
        show_main_menu,
        show_login_menu,
        show_settings_menu,
        show_help,
        show_download_result,
        get_url_input,
        get_file_input,
        show_progress_header,
        show_platform_detection,
        confirm_download,
    )
    from .xiaohongshu import XiaohongshuDownloader
    from .weibo import WeiboDownloader
except ImportError:
    from src.ui import (
        clear_screen,
        print_banner,
        print_logo_small,
        show_main_menu,
        show_login_menu,
        show_settings_menu,
        show_help,
        show_download_result,
        get_url_input,
        get_file_input,
        show_progress_header,
        show_platform_detection,
        confirm_download,
    )
    from src.xiaohongshu import XiaohongshuDownloader
    from src.weibo import WeiboDownloader

console = Console()


def detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL."""
    url_lower = url.lower()
    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xiaohongshu"
    elif "weibo.com" in url_lower or "weibo.cn" in url_lower:
        return "weibo"
    return None


class App:
    """Main application class."""

    def __init__(self):
        self.settings = {
            "comments": True,
            "images": True,
            "max_comments": 50,
            "delay": 3.0,
            "output": Path("./downloads"),
        }
        self.xhs_logged_in = False
        self.weibo_logged_in = False

    async def check_login_status(self):
        """Check login status for both platforms."""
        with console.status("[cyan]检查登录状态...[/cyan]"):
            try:
                async with XiaohongshuDownloader() as xhs:
                    self.xhs_logged_in = await xhs.check_login()
            except Exception:
                self.xhs_logged_in = False

            try:
                async with WeiboDownloader() as weibo:
                    self.weibo_logged_in = await weibo.check_login()
            except Exception:
                self.weibo_logged_in = False

    def show_login_status(self):
        """Display login status."""
        table = Table(box=ROUNDED, border_style="cyan")
        table.add_column("平台", style="bold")
        table.add_column("状态")

        table.add_row(
            "🔴 小红书",
            "[green]已登录 ✓[/green]" if self.xhs_logged_in else "[red]未登录 ✗[/red]"
        )
        table.add_row(
            "🟡 微博",
            "[green]已登录 ✓[/green]" if self.weibo_logged_in else "[red]未登录 ✗[/red]"
        )

        console.print(Panel(table, title="登录状态", border_style="cyan"))

    async def login_xiaohongshu(self):
        """Login to Xiaohongshu."""
        console.print("\n[cyan]正在启动小红书登录...[/cyan]")
        console.print("[yellow]请在浏览器中完成登录（扫码或手动登录）[/yellow]")
        console.print("[dim]登录完成后按 Enter 键继续[/dim]\n")

        try:
            async with XiaohongshuDownloader() as xhs:
                await xhs.login()
                self.xhs_logged_in = True
        except Exception as e:
            console.print(f"[red]登录失败: {e}[/red]")

    async def login_weibo(self):
        """Login to Weibo."""
        console.print("\n[cyan]正在启动微博登录...[/cyan]")
        console.print("[yellow]请在浏览器中完成登录[/yellow]")
        console.print("[dim]登录完成后按 Enter 键继续[/dim]\n")

        try:
            async with WeiboDownloader() as weibo:
                await weibo.login()
                self.weibo_logged_in = True
        except Exception as e:
            console.print(f"[red]登录失败: {e}[/red]")

    async def download_single(self, url: str) -> bool:
        """Download a single URL."""
        platform = detect_platform(url)
        show_platform_detection(url, platform)

        if not platform:
            console.print("[red]无法识别的 URL 格式[/red]")
            return False

        if platform == "xiaohongshu":
            if not self.xhs_logged_in:
                console.print("[yellow]小红书未登录，正在启动登录...[/yellow]")
                await self.login_xiaohongshu()
                if not self.xhs_logged_in:
                    return False

            async with XiaohongshuDownloader() as xhs:
                output_dir = self.settings["output"] / "xiaohongshu"
                result = await xhs.download(
                    url=url,
                    output_dir=output_dir,
                    fetch_comments=self.settings["comments"],
                    max_comments=self.settings["max_comments"],
                    download_images=self.settings["images"],
                )
                return result is not None

        elif platform == "weibo":
            if not self.weibo_logged_in:
                console.print("[yellow]微博未登录，正在启动登录...[/yellow]")
                await self.login_weibo()
                if not self.weibo_logged_in:
                    return False

            async with WeiboDownloader() as weibo:
                output_dir = self.settings["output"] / "weibo"
                result = await weibo.download(
                    url=url,
                    output_dir=output_dir,
                    fetch_comments=self.settings["comments"],
                    max_comments=self.settings["max_comments"],
                    download_images=self.settings["images"],
                )
                return result is not None

        return False

    async def download_batch(self, urls: List[str]):
        """Download multiple URLs."""
        if not urls:
            console.print("[yellow]没有有效的 URL[/yellow]")
            return

        # Group by platform
        xhs_urls = [u for u in urls if detect_platform(u) == "xiaohongshu"]
        weibo_urls = [u for u in urls if detect_platform(u) == "weibo"]
        unknown = [u for u in urls if detect_platform(u) is None]

        if unknown:
            console.print(f"[yellow]跳过 {len(unknown)} 个无法识别的 URL[/yellow]")

        total = len(xhs_urls) + len(weibo_urls)
        if not confirm_download(total, self.settings):
            return

        success = 0
        failed = 0

        # Download Xiaohongshu
        if xhs_urls:
            if not self.xhs_logged_in:
                console.print("\n[yellow]小红书未登录，正在启动登录...[/yellow]")
                await self.login_xiaohongshu()

            if self.xhs_logged_in:
                async with XiaohongshuDownloader() as xhs:
                    output_dir = self.settings["output"] / "xiaohongshu"

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        TimeElapsedColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("[cyan]下载小红书...", total=len(xhs_urls))

                        for i, url in enumerate(xhs_urls):
                            progress.update(task, description=f"[cyan]小红书 ({i+1}/{len(xhs_urls)})")

                            try:
                                result = await xhs.download(
                                    url=url,
                                    output_dir=output_dir,
                                    fetch_comments=self.settings["comments"],
                                    max_comments=self.settings["max_comments"],
                                    download_images=self.settings["images"],
                                )
                                if result:
                                    success += 1
                                else:
                                    failed += 1
                            except Exception as e:
                                console.print(f"[dim]错误: {e}[/dim]")
                                failed += 1

                            progress.update(task, advance=1)

                            if i < len(xhs_urls) - 1:
                                await asyncio.sleep(self.settings["delay"])
            else:
                failed += len(xhs_urls)

        # Download Weibo
        if weibo_urls:
            if not self.weibo_logged_in:
                console.print("\n[yellow]微博未登录，正在启动登录...[/yellow]")
                await self.login_weibo()

            if self.weibo_logged_in:
                async with WeiboDownloader() as weibo:
                    output_dir = self.settings["output"] / "weibo"

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        TimeElapsedColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("[yellow]下载微博...", total=len(weibo_urls))

                        for i, url in enumerate(weibo_urls):
                            progress.update(task, description=f"[yellow]微博 ({i+1}/{len(weibo_urls)})")

                            try:
                                result = await weibo.download(
                                    url=url,
                                    output_dir=output_dir,
                                    fetch_comments=self.settings["comments"],
                                    max_comments=self.settings["max_comments"],
                                    download_images=self.settings["images"],
                                )
                                if result:
                                    success += 1
                                else:
                                    failed += 1
                            except Exception as e:
                                console.print(f"[dim]错误: {e}[/dim]")
                                failed += 1

                            progress.update(task, advance=1)

                            if i < len(weibo_urls) - 1:
                                await asyncio.sleep(self.settings["delay"])
            else:
                failed += len(weibo_urls)

        show_download_result(success, failed, self.settings["output"])

    async def handle_download(self):
        """Handle single download menu."""
        while True:
            url = get_url_input()
            if url.lower() == 'q':
                break

            if url:
                await self.download_single(url)

            if not Confirm.ask("\n继续下载?", default=True):
                break

    async def handle_batch_download(self):
        """Handle batch download menu."""
        file_path = get_file_input()
        if not file_path:
            return

        # Read URLs from file
        urls = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

        if not urls:
            console.print("[yellow]文件中没有找到有效的 URL[/yellow]")
            return

        console.print(f"\n[cyan]找到 {len(urls)} 个 URL[/cyan]")
        await self.download_batch(urls)

    async def handle_login_menu(self):
        """Handle login menu."""
        while True:
            choice = show_login_menu()

            if choice == "0":
                break
            elif choice == "1":
                await self.login_xiaohongshu()
            elif choice == "2":
                await self.login_weibo()
            elif choice == "3":
                await self.check_login_status()
                self.show_login_status()

            Prompt.ask("\n[dim]按 Enter 继续[/dim]", default="")

    async def run(self):
        """Run the application."""
        clear_screen()
        print_banner()

        # Check login status on startup
        await self.check_login_status()

        while True:
            print_logo_small()
            self.show_login_status()
            choice = show_main_menu()

            if choice == "0":
                console.print("\n[cyan]再见! 👋[/cyan]\n")
                break
            elif choice == "1":
                await self.handle_download()
            elif choice == "2":
                await self.handle_batch_download()
            elif choice == "3":
                await self.handle_login_menu()
            elif choice == "4":
                self.settings = show_settings_menu(self.settings)
            elif choice == "5":
                show_help()

            if choice != "0":
                console.print()


def main():
    """Main entry point."""
    try:
        app = App()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]已取消[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]发生错误: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
