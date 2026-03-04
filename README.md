# Social Media Downloader

下载小红书和微博内容的命令行工具，支持下载图片、文字和评论。

## 功能特性

- **自动识别平台**: 根据 URL 自动识别小红书或微博
- **完整内容下载**: 文字、图片、评论一键下载
- **批量下载**: 支持从文件读取 URL 列表
- **登录状态管理**: 自动保存登录状态，无需重复登录
- **可打包成 EXE**: 支持 PyInstaller 打包为独立可执行文件

## 安装

### 方式一：使用 Poetry（推荐开发）

```bash
# 克隆项目
cd social-media-downloader

# 安装依赖
poetry install

# 安装 Playwright 浏览器
poetry run playwright install chromium

# 运行
poetry run smd --help
```

### 方式二：使用 pip

```bash
pip install playwright httpx typer rich pydantic beautifulsoup4 lxml
playwright install chromium
python -m src.main --help
```

## 使用方法

### 交互模式

直接运行 `smd` 不带任何参数即可进入交互模式：

```bash
smd
```

交互模式提供：
- 精美的终端 UI 界面
- 菜单式操作
- 登录状态显示
- 批量下载进度条
- 设置管理

### 1. 首次使用 - 登录

```bash
# 登录小红书
smd login xhs

# 登录微博
smd login weibo
```

登录时会打开浏览器，请手动完成登录后按 Enter 键。登录状态会自动保存。

### 2. 检查登录状态

```bash
smd status
```

### 3. 下载单个内容

```bash
# 小红书
smd download "https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy"

# 微博
smd download "https://weibo.com/1234567890/AbCdEfGhI"

# 指定输出目录
smd download "URL" -o ./my_downloads

# 不下载评论
smd download "URL" --no-comments

# 不下载图片
smd download "URL" --no-images
```

### 4. 批量下载

创建一个 `urls.txt` 文件，每行一个 URL：

```
# 小红书
https://www.xiaohongshu.com/explore/xxx
https://www.xiaohongshu.com/explore/yyy

# 微博
https://weibo.com/1234/AbCdEf
https://weibo.com/5678/GhIjKl
```

然后运行：

```bash
smd batch urls.txt -o ./downloads --delay 5
```

### 5. 混合下载

可以同时传入小红书和微博的 URL：

```bash
smd download "小红书URL" "微博URL" "另一个URL"
```

## 输出结构

```
downloads/
├── xiaohongshu/
│   ├── note_id_1/
│   │   ├── image_01.jpg
│   │   ├── image_02.jpg
│   │   └── ...
│   ├── note_id_1.json      # 完整内容（含评论）
│   └── ...
└── weibo/
    ├── mid_1/
    │   ├── image_01.jpg
    │   └── ...
    ├── mid_1.json
    └── ...
```

## 打包成 EXE

### Windows

```bash
# 安装 PyInstaller
pip install pyinstaller

# 运行打包脚本
python build.py

# 或手动打包
pyinstaller smd.spec
```

打包后的可执行文件在 `dist/smd.exe`。

### 注意事项

1. **Playwright 浏览器**: 打包后运行前需要在目标机器上安装 Playwright 浏览器：
   ```bash
   playwright install chromium
   ```

2. **首次运行**: 首次运行需要登录，会打开浏览器窗口。

3. **登录状态**: 登录状态保存在用户目录：
   - Windows: `C:\Users\<用户名>\.social_media_downloader\`
   - macOS/Linux: `~/.social_media_downloader/`

## 命令参考

```
smd --help                    # 显示帮助
smd download --help           # 下载命令帮助
smd batch --help              # 批量下载帮助

smd login xhs                 # 登录小红书
smd login weibo               # 登录微博
smd status                    # 检查登录状态

smd download URL [URL...]     # 下载一个或多个 URL
  -o, --output PATH           # 输出目录（默认 ./downloads）
  --comments/--no-comments    # 是否下载评论（默认是）
  --max-comments N            # 最大评论数（默认 50）
  --images/--no-images        # 是否下载图片（默认是）

smd batch FILE                # 从文件批量下载
  -o, --output PATH           # 输出目录
  --delay SECONDS             # 请求间隔（默认 3 秒）
```

## 技术栈

- Python 3.11+
- Playwright (浏览器自动化)
- httpx (HTTP 客户端)
- Typer (CLI 框架)
- Rich (终端 UI)
- Pydantic (数据模型)
- PyInstaller (打包)

## 免责声明

本工具仅供学习研究使用，请遵守相关平台的服务条款和法律法规。
