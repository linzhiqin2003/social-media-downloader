"""Beautiful interactive UI for Social Media Downloader."""

import os
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.box import DOUBLE, ROUNDED
from rich.style import Style
from rich.live import Live
from rich.layout import Layout
from rich.markdown import Markdown

console = Console()

# Color theme
THEME = {
    "primary": "cyan",
    "secondary": "magenta",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "dim": "dim white",
    "highlight": "bold cyan",
}


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """Print beautiful app banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   ███████╗███╗   ███╗██████╗                                              ║
║   ██╔════╝████╗ ████║██╔══██╗                                             ║
║   ███████╗██╔████╔██║██║  ██║  Social Media Downloader                    ║
║   ╚════██║██║╚██╔╝██║██║  ██║  小红书 & 微博 内容下载器                   ║
║   ███████║██║ ╚═╝ ██║██████╔╝  v1.0.0                                     ║
║   ╚══════╝╚═╝     ╚═╝╚═════╝                                              ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def print_logo_small():
    """Print small logo."""
    logo = Text()
    logo.append("📱 ", style="bold")
    logo.append("Social Media Downloader", style="bold cyan")
    logo.append(" v1.0", style="dim")
    console.print(logo)
    console.print()


def show_main_menu() -> str:
    """Show main menu and get user choice."""
    console.print()

    # Create menu table
    menu = Table(
        show_header=False,
        box=ROUNDED,
        border_style="cyan",
        padding=(0, 2),
        expand=False,
    )
    menu.add_column("Key", style="bold yellow", width=6)
    menu.add_column("Option", style="white")
    menu.add_column("Description", style="dim")

    menu.add_row("1", "📥 下载内容", "输入 URL 下载小红书/微博内容")
    menu.add_row("2", "📋 批量下载", "从文件读取多个 URL 批量下载")
    menu.add_row("3", "🔐 登录管理", "登录/查看登录状态")
    menu.add_row("4", "⚙️  设置", "配置下载选项")
    menu.add_row("5", "❓ 帮助", "查看使用说明")
    menu.add_row("0", "🚪 退出", "退出程序")

    console.print(Panel(menu, title="[bold]主菜单[/bold]", border_style="cyan"))

    choice = Prompt.ask(
        "\n[bold cyan]请选择[/bold cyan]",
        choices=["0", "1", "2", "3", "4", "5"],
        default="1"
    )
    return choice


def show_login_menu() -> str:
    """Show login menu."""
    console.print()

    menu = Table(show_header=False, box=ROUNDED, border_style="magenta", padding=(0, 2))
    menu.add_column("Key", style="bold yellow", width=6)
    menu.add_column("Option", style="white")

    menu.add_row("1", "🔴 登录小红书")
    menu.add_row("2", "🟡 登录微博")
    menu.add_row("3", "📊 查看登录状态")
    menu.add_row("0", "⬅️  返回主菜单")

    console.print(Panel(menu, title="[bold]登录管理[/bold]", border_style="magenta"))

    return Prompt.ask(
        "\n[bold magenta]请选择[/bold magenta]",
        choices=["0", "1", "2", "3"],
        default="3"
    )


def show_settings_menu(settings: dict) -> dict:
    """Show and edit settings."""
    console.print()

    # Display current settings
    table = Table(title="当前设置", box=ROUNDED, border_style="green")
    table.add_column("选项", style="cyan")
    table.add_column("当前值", style="yellow")
    table.add_column("说明", style="dim")

    table.add_row("1. 下载评论", "✅ 是" if settings["comments"] else "❌ 否", "是否下载评论内容")
    table.add_row("2. 下载图片", "✅ 是" if settings["images"] else "❌ 否", "是否下载图片到本地")
    table.add_row("3. 最大评论数", str(settings["max_comments"]), "每个帖子最大评论数")
    table.add_row("4. 请求间隔", f"{settings['delay']}秒", "批量下载时请求间隔")
    table.add_row("5. 输出目录", str(settings["output"]), "内容保存位置")

    console.print(table)
    console.print("\n[dim]输入选项编号修改设置，输入 0 返回[/dim]")

    choice = Prompt.ask(
        "\n[bold green]选择要修改的项[/bold green]",
        choices=["0", "1", "2", "3", "4", "5"],
        default="0"
    )

    if choice == "1":
        settings["comments"] = Confirm.ask("下载评论?", default=settings["comments"])
    elif choice == "2":
        settings["images"] = Confirm.ask("下载图片?", default=settings["images"])
    elif choice == "3":
        settings["max_comments"] = int(Prompt.ask("最大评论数", default=str(settings["max_comments"])))
    elif choice == "4":
        settings["delay"] = float(Prompt.ask("请求间隔(秒)", default=str(settings["delay"])))
    elif choice == "5":
        settings["output"] = Path(Prompt.ask("输出目录", default=str(settings["output"])))

    return settings


def show_help():
    """Show help information."""
    help_text = """
## 使用说明

### 支持的平台
- **小红书**: xiaohongshu.com, xhslink.com
- **微博**: weibo.com, m.weibo.cn

### URL 格式示例

**小红书:**
```
https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy
```

**微博:**
```
https://weibo.com/1234567890/AbCdEfGhI
https://m.weibo.cn/detail/4567890123456789
```

### 批量下载

创建文本文件，每行一个 URL，支持注释（以 # 开头）:
```
# 小红书
https://www.xiaohongshu.com/explore/xxx

# 微博
https://weibo.com/1234/AbCdEf
```

### 输出结构
```
downloads/
├── xiaohongshu/
│   ├── note_id/
│   │   ├── image_01.jpg
│   │   └── ...
│   └── note_id.json
└── weibo/
    ├── mid/
    │   └── image_01.jpg
    └── mid.json
```

### 注意事项
1. 首次使用需要登录（扫码或手动登录）
2. 登录状态会自动保存
3. 下载间隔建议不低于 3 秒
    """

    console.print(Panel(
        Markdown(help_text),
        title="[bold]帮助文档[/bold]",
        border_style="blue",
        padding=(1, 2)
    ))

    Prompt.ask("\n[dim]按 Enter 返回[/dim]", default="")


def show_download_result(success: int, failed: int, output_dir: Path):
    """Show download result summary."""
    console.print()

    # Result panel
    if failed == 0:
        style = "green"
        icon = "✅"
        status = "全部成功"
    elif success == 0:
        style = "red"
        icon = "❌"
        status = "全部失败"
    else:
        style = "yellow"
        icon = "⚠️"
        status = "部分成功"

    result = Table.grid(padding=1)
    result.add_column(justify="center")
    result.add_row(f"[bold {style}]{icon} {status}[/bold {style}]")
    result.add_row(f"[green]成功: {success}[/green] | [red]失败: {failed}[/red]")
    result.add_row(f"[dim]保存位置: {output_dir}[/dim]")

    console.print(Panel(result, border_style=style))


def get_url_input() -> str:
    """Get URL input from user."""
    console.print()
    console.print("[bold cyan]请输入 URL[/bold cyan]")
    console.print("[dim]支持小红书和微博链接，输入 'q' 返回[/dim]")
    console.print()

    url = Prompt.ask("[cyan]URL[/cyan]")
    return url.strip()


def get_file_input() -> Optional[Path]:
    """Get file path input from user."""
    console.print()
    console.print("[bold cyan]请输入 URL 列表文件路径[/bold cyan]")
    console.print("[dim]文件中每行一个 URL，支持 # 注释[/dim]")
    console.print()

    path_str = Prompt.ask("[cyan]文件路径[/cyan]")
    if path_str.lower() == 'q':
        return None

    path = Path(path_str)
    if not path.exists():
        console.print(f"[red]文件不存在: {path}[/red]")
        return None

    return path


def show_progress_header(platform: str, current: int, total: int, url: str):
    """Show progress header during download."""
    console.print()
    console.rule(f"[bold cyan]{platform}[/bold cyan] ({current}/{total})")
    console.print(f"[dim]{url[:60]}{'...' if len(url) > 60 else ''}[/dim]")


def show_platform_detection(url: str, platform: Optional[str]):
    """Show platform detection result."""
    if platform == "xiaohongshu":
        console.print(f"[red]●[/red] 检测到: [bold]小红书[/bold]")
    elif platform == "weibo":
        console.print(f"[yellow]●[/yellow] 检测到: [bold]微博[/bold]")
    else:
        console.print(f"[dim]●[/dim] [yellow]未知平台[/yellow]")


def confirm_download(count: int, settings: dict) -> bool:
    """Confirm before starting download."""
    console.print()

    info = Table.grid(padding=(0, 2))
    info.add_column(style="cyan")
    info.add_column(style="white")

    info.add_row("待下载数量:", f"{count} 个")
    info.add_row("下载评论:", "是" if settings["comments"] else "否")
    info.add_row("下载图片:", "是" if settings["images"] else "否")
    info.add_row("输出目录:", str(settings["output"]))

    console.print(Panel(info, title="下载确认", border_style="cyan"))

    return Confirm.ask("\n开始下载?", default=True)
