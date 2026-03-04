# Social Media Downloader

下载小红书和微博内容的桌面应用，支持下载图片、文字和评论。

## 功能特性

- **桌面 GUI**: PyQt5 图形界面，双击即用，无需命令行
- **自动识别平台**: 根据 URL 自动识别小红书或微博
- **完整内容下载**: 文字、图片、评论一键下载
- **Cookie 导入**: 通过 GUI 弹窗粘贴 Cookie，一键登录
- **CLI 模式**: 保留完整命令行支持（`--cli` 参数）
- **跨平台打包**: 支持 macOS / Windows / Linux

## 截图

```
┌─────────────────────────────────────────────┐
│  Social Media Downloader                     │
├─────────────────────────────────────────────┤
│  登录状态:                                   │
│  小红书: 已登录 ✓  [导入Cookie]              │
│  微博:   未登录 ✗  [导入Cookie]              │
├─────────────────────────────────────────────┤
│  URL: [________________________] [下载]       │
│  输出目录: [./downloads        ] [选择...]     │
│  ☑ 下载图片  ☑ 抓取评论  评论数: [50]         │
├─────────────────────────────────────────────┤
│  下载进度: ████████████░░░░ 60%              │
├─────────────────────────────────────────────┤
│  日志输出:                                   │
│  [02:30:01] 检测到平台: xiaohongshu          │
│  [02:30:02] 正在获取内容...                   │
│  [02:30:05] [OK] 下载完成: xxx (5 张图片)     │
└─────────────────────────────────────────────┘
```

## 安装

### 方式一：下载可执行文件（推荐）

从 [Releases](../../releases) 页面下载对应平台的安装包：

| 平台 | 文件 | 说明 |
|------|------|------|
| Windows | `smd-windows-x64.zip` | 解压后运行 `smd/smd.exe` |
| macOS (Apple Silicon) | `SocialMediaDownloader-macOS-arm64.zip` | 解压得到 `.app`，双击使用 |
| Linux | `smd-linux-x64.tar.gz` | 解压后运行 `smd/smd` |

### 方式二：从源码运行

```bash
cd social-media-downloader

# 安装依赖
poetry install

# 启动 GUI
poetry run python entry.py

# 或启动 CLI 模式
poetry run python entry.py --cli
poetry run smd --help
```

## 使用方法

### GUI 模式（默认）

1. **导入 Cookie**: 点击「导入Cookie」按钮，按照弹窗指引从浏览器导出 Cookie 并粘贴
2. **输入 URL**: 在 URL 输入框粘贴小红书或微博链接
3. **点击下载**: 进度条和日志区域会实时显示下载进度
4. **查看结果**: 下载的内容保存在输出目录中

### CLI 模式

通过 `--cli` 参数或 `smd` 命令使用：

```bash
# 交互模式
smd

# 登录
smd login xhs
smd login weibo

# 检查登录状态
smd status

# 下载单个内容
smd download "https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy"
smd download "https://weibo.com/1234567890/AbCdEfGhI"

# 指定输出目录 / 跳过评论 / 跳过图片
smd download "URL" -o ./my_downloads --no-comments --no-images

# 批量下载
smd batch urls.txt -o ./downloads --delay 5

# 混合下载
smd download "小红书URL" "微博URL"
```

## 输出结构

```
downloads/
├── xiaohongshu/
│   ├── note_id_1/
│   │   ├── image_01.jpg
│   │   ├── image_02.jpg
│   │   └── ...
│   ├── note_id_1.json      # 完整内容（含元数据）
│   └── ...
└── weibo/
    ├── mid_1/
    │   ├── image_01.jpg
    │   └── ...
    ├── mid_1.json           # 完整内容（含评论）
    └── ...
```

## 打包

### macOS

```bash
# 安装 PyInstaller
poetry run pip install pyinstaller

# 构建 .app + DMG
python build_dmg.py
```

### Windows / Linux

```bash
python build.py
```

打包后的文件在 `dist/` 目录。

## 命令参考

```
smd --help                    # 显示帮助
smd download URL [URL...]     # 下载一个或多个 URL
  -o, --output PATH           # 输出目录（默认 ./downloads）
  --no-comments               # 跳过评论
  --max-comments N            # 最大评论数（默认 50）
  --no-images                 # 跳过图片

smd batch FILE                # 从文件批量下载
  --delay SECONDS             # 请求间隔（默认 3 秒）

smd login xhs|weibo           # 登录平台
smd status                    # 检查登录状态
```

## 技术栈

- Python 3.11+
- PyQt5 (桌面 GUI)
- httpx (HTTP 客户端)
- Typer (CLI 框架)
- Rich (终端 UI)
- Pydantic (数据模型)
- PyInstaller (打包)

## 登录状态存储

登录 Cookie 保存在用户目录：
- macOS/Linux: `~/.social_media_downloader/`
- Windows: `C:\Users\<用户名>\.social_media_downloader\`

## 免责声明

本工具仅供学习研究使用，请遵守相关平台的服务条款和法律法规。
