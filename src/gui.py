"""PySide6 GUI for Social Media Downloader."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from .xiaohongshu import XiaohongshuDownloader
    from .weibo import WeiboDownloader
except ImportError:
    from src.xiaohongshu import XiaohongshuDownloader
    from src.weibo import WeiboDownloader


# ---- Worker thread for async downloads ----

class DownloadWorker(QThread):
    """Runs async download in a separate thread."""

    log = Signal(str)
    progress = Signal(int, int)
    finished_ok = Signal(bool, str)

    def __init__(self, url, output_dir, fetch_comments, max_comments, download_images):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.fetch_comments = fetch_comments
        self.max_comments = max_comments
        self.download_images = download_images

    def _detect_platform(self, url):
        url_lower = url.lower()
        if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
            return "xiaohongshu"
        elif "weibo.com" in url_lower or "weibo.cn" in url_lower:
            return "weibo"
        return None

    def run(self):
        try:
            asyncio.run(self._download())
        except Exception as e:
            self.finished_ok.emit(False, str(e))

    async def _download(self):
        platform = self._detect_platform(self.url)
        if not platform:
            self.finished_ok.emit(False, "无法识别的 URL 格式")
            return

        self.log.emit(f"检测到平台: {platform}")
        self.progress.emit(0, 100)

        if platform == "xiaohongshu":
            downloader = XiaohongshuDownloader()
            out = self.output_dir / "xiaohongshu"
        else:
            downloader = WeiboDownloader()
            out = self.output_dir / "weibo"

        if not await downloader.check_login():
            self.finished_ok.emit(False, f"{platform} 未登录，请先导入 Cookie")
            return

        self.log.emit("正在获取内容...")
        self.progress.emit(30, 100)

        result = await downloader.download(
            url=self.url,
            output_dir=out,
            fetch_comments=self.fetch_comments,
            max_comments=self.max_comments,
            download_images=self.download_images,
        )

        self.progress.emit(100, 100)

        if result:
            if platform == "xiaohongshu":
                title = getattr(result, "title", "") or result.note_id
                n_images = len(result.images)
                self.finished_ok.emit(True, f"下载完成: {title} ({n_images} 张图片)")
            else:
                mid = result.mid
                n_images = len(result.images)
                n_comments = len(result.comments)
                self.finished_ok.emit(
                    True, f"下载完成: {mid} ({n_images} 张图片, {n_comments} 条评论)"
                )
        else:
            self.finished_ok.emit(False, "下载失败，请检查 URL 和登录状态")


class LoginCheckWorker(QThread):
    """Check login status in background."""

    result = Signal(bool, bool)

    def run(self):
        try:
            asyncio.run(self._check())
        except Exception:
            self.result.emit(False, False)

    async def _check(self):
        xhs_ok = False
        weibo_ok = False
        try:
            xhs = XiaohongshuDownloader()
            xhs_ok = await xhs.check_login()
        except Exception:
            pass
        try:
            weibo = WeiboDownloader()
            weibo_ok = await weibo.check_login()
        except Exception:
            pass
        self.result.emit(xhs_ok, weibo_ok)


# ---- Cookie Import Dialog ----

class CookieDialog(QDialog):
    """Dialog for pasting cookies."""

    def __init__(self, platform_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"导入 {platform_name} Cookie")
        self.setMinimumSize(500, 350)
        self.cookie_text = ""

        layout = QVBoxLayout(self)

        instructions = QLabel(
            f"<b>{platform_name} Cookie 导入</b><br><br>"
            "1. 在浏览器中打开对应网站并登录<br>"
            "2. 按 F12 → 控制台 (Console)<br>"
            "3. 粘贴以下代码并回车："
        )
        instructions.setWordWrap(True)
        instructions.setTextFormat(Qt.RichText)
        layout.addWidget(instructions)

        js_code = (
            "copy(document.cookie.split('; ')"
            ".map(c => { const [n,...v] = c.split('='); "
            "return {name:n, value:v.join('=')} }))"
        )
        code_row = QHBoxLayout()
        code_field = QLineEdit(js_code)
        code_field.setReadOnly(True)
        code_field.setStyleSheet("background: #f0f0f0; font-family: monospace; padding: 4px;")
        code_row.addWidget(code_field, 1)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(60)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(js_code))
        code_row.addWidget(copy_btn)
        layout.addLayout(code_row)

        step4 = QLabel("4. 将剪贴板内容粘贴到下方：")
        layout.addWidget(step4)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在此粘贴 Cookie JSON 或原始字符串...")
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_ok.clicked.connect(self._accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _accept(self):
        self.cookie_text = self.text_edit.toPlainText().strip()
        if self.cookie_text:
            self.accept()


# ---- Main Window ----

class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Social Media Downloader")
        self.setMinimumSize(600, 520)
        self.resize(640, 580)

        self.xhs_logged_in = False
        self.weibo_logged_in = False
        self.worker: Optional[DownloadWorker] = None

        self._build_ui()
        self._check_login()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # ---- Login status ----
        login_group = QGroupBox("登录状态")
        login_layout = QVBoxLayout(login_group)

        xhs_row = QHBoxLayout()
        self.xhs_status_label = QLabel("小红书: 检查中...")
        xhs_row.addWidget(self.xhs_status_label, 1)
        self.xhs_cookie_btn = QPushButton("导入Cookie")
        self.xhs_cookie_btn.setFixedWidth(100)
        self.xhs_cookie_btn.clicked.connect(lambda: self._import_cookie("xiaohongshu"))
        xhs_row.addWidget(self.xhs_cookie_btn)
        login_layout.addLayout(xhs_row)

        weibo_row = QHBoxLayout()
        self.weibo_status_label = QLabel("微博: 检查中...")
        weibo_row.addWidget(self.weibo_status_label, 1)
        self.weibo_cookie_btn = QPushButton("导入Cookie")
        self.weibo_cookie_btn.setFixedWidth(100)
        self.weibo_cookie_btn.clicked.connect(lambda: self._import_cookie("weibo"))
        weibo_row.addWidget(self.weibo_cookie_btn)
        login_layout.addLayout(weibo_row)

        root.addWidget(login_group)

        # ---- Download settings ----
        settings_group = QGroupBox("下载设置")
        settings_layout = QVBoxLayout(settings_group)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴小红书或微博链接...")
        self.url_input.returnPressed.connect(self._start_download)
        url_row.addWidget(self.url_input, 1)
        self.download_btn = QPushButton("下载")
        self.download_btn.setFixedWidth(80)
        self.download_btn.clicked.connect(self._start_download)
        url_row.addWidget(self.download_btn)
        settings_layout.addLayout(url_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("输出目录:"))
        self.output_input = QLineEdit(str(Path("./downloads").resolve()))
        dir_row.addWidget(self.output_input, 1)
        browse_btn = QPushButton("选择...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_output)
        dir_row.addWidget(browse_btn)
        settings_layout.addLayout(dir_row)

        opts_row = QHBoxLayout()
        self.chk_images = QCheckBox("下载图片")
        self.chk_images.setChecked(True)
        opts_row.addWidget(self.chk_images)
        self.chk_comments = QCheckBox("抓取评论")
        self.chk_comments.setChecked(True)
        opts_row.addWidget(self.chk_comments)
        opts_row.addWidget(QLabel("评论数:"))
        self.spin_comments = QSpinBox()
        self.spin_comments.setRange(1, 500)
        self.spin_comments.setValue(50)
        self.spin_comments.setFixedWidth(80)
        opts_row.addWidget(self.spin_comments)
        opts_row.addStretch()
        settings_layout.addLayout(opts_row)

        root.addWidget(settings_group)

        # ---- Progress ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        root.addWidget(self.progress_bar)

        # ---- Log output ----
        log_group = QGroupBox("日志输出")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        font = QFont("Menlo" if sys.platform == "darwin" else "Consolas", 11)
        self.log_view.setFont(font)
        log_layout.addWidget(self.log_view)
        root.addWidget(log_group, 1)

    # ---- Login status ----

    def _check_login(self):
        self.login_worker = LoginCheckWorker()
        self.login_worker.result.connect(self._on_login_checked)
        self.login_worker.start()

    def _on_login_checked(self, xhs_ok, weibo_ok):
        self.xhs_logged_in = xhs_ok
        self.weibo_logged_in = weibo_ok
        self._update_login_labels()

    def _update_login_labels(self):
        if self.xhs_logged_in:
            self.xhs_status_label.setText("小红书: 已登录 \u2714")
            self.xhs_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.xhs_status_label.setText("小红书: 未登录 \u2718")
            self.xhs_status_label.setStyleSheet("color: red;")

        if self.weibo_logged_in:
            self.weibo_status_label.setText("微博: 已登录 \u2714")
            self.weibo_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.weibo_status_label.setText("微博: 未登录 \u2718")
            self.weibo_status_label.setStyleSheet("color: red;")

    # ---- Cookie import ----

    def _import_cookie(self, platform):
        name = "小红书" if platform == "xiaohongshu" else "微博"
        dlg = CookieDialog(name, self)
        if dlg.exec() != QDialog.Accepted:
            return

        raw = dlg.cookie_text
        if platform == "xiaohongshu":
            downloader = XiaohongshuDownloader()
            ok = downloader.import_cookies(raw)
            self.xhs_logged_in = ok
        else:
            downloader = WeiboDownloader()
            ok = downloader.import_cookies(raw)
            self.weibo_logged_in = ok

        self._update_login_labels()
        if ok:
            self._log(f"{name} Cookie 导入成功")
        else:
            self._log(f"{name} Cookie 导入失败或缺少关键字段")

    # ---- Output directory ----

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_input.text())
        if path:
            self.output_input.setText(path)

    # ---- Download ----

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self._log("请输入 URL")
            return

        if self.worker and self.worker.isRunning():
            self._log("下载进行中，请等待完成")
            return

        output_dir = Path(self.output_input.text())
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(False)

        self.worker = DownloadWorker(
            url=url,
            output_dir=output_dir,
            fetch_comments=self.chk_comments.isChecked(),
            max_comments=self.spin_comments.value(),
            download_images=self.chk_images.isChecked(),
        )
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_download_done)
        self.worker.start()

    def _on_progress(self, current, total):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def _on_download_done(self, success, message):
        self.download_btn.setEnabled(True)
        if success:
            self._log(f"[OK] {message}")
        else:
            self._log(f"[ERROR] {message}")

    # ---- Logging ----

    def _log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {text}")


# ---- Entry ----

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Social Media Downloader")

    icon_paths = [
        Path(__file__).parent.parent / "assets" / "icon.png",
        Path(__file__).parent.parent / "assets" / "icon.icns",
    ]
    for p in icon_paths:
        if p.exists():
            app.setWindowIcon(QIcon(str(p)))
            break

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
