# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""macOS 入口:起本地服务 + 原生窗口(WKWebView),双击即用,不占浏览器标签页。

开发/调试:
    python -m wlmac.app            # 打开原生窗口
    WL_HEADLESS=1 python -m wlmac.app   # 只起服务,打印地址(自动化测试用)
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

from werkzeug.serving import make_server

from . import APP_NAME, __version__
from .service import service
from .web import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int):
    app = create_app(service)
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="wl-http", daemon=True)
    thread.start()
    return server


def _style_titlebar(*_args) -> None:
    """让标题栏与页面顶栏同色,消掉深浅两色的接缝。

    NSWindow 的几何/外观只能在主线程改,事件回调在子线程,所以用 callAfter 转投;
    任何一步失败都不影响功能,只是保留系统默认外观。
    """
    try:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(_apply_titlebar_style)
    except Exception:
        pass


def _apply_titlebar_style() -> None:
    try:
        import webview
        from AppKit import NSApp, NSColor

        native = webview.windows[0].native
        dark = "Dark" in str(NSApp.effectiveAppearance().name())
        if dark:
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(0.086, 0.094, 0.110, 1.0)
        else:
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 1.0)
        native.setTitlebarAppearsTransparent_(True)
        native.setBackgroundColor_(color)
        native.setTitleVisibility_(1)   # 1 = NSWindowTitleHidden:标题在页面里已经写了,不再重复
        # pywebview 会把标题栏容器视图刷成 windowBackgroundColor,这里一并覆盖
        native.contentView().superview().subviews().lastObject().setBackgroundColor_(color)
    except Exception:
        pass


def main() -> int:
    port = int(os.environ.get("WL_PORT") or _free_port())
    server = _start_server(port)
    url = f"http://127.0.0.1:{port}/"

    if os.environ.get("WL_HEADLESS") == "1":
        print(f"WL_URL={url}", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            service.shutdown()
            server.shutdown()
        return 0

    try:
        import webview
    except Exception as exc:  # 没有 pywebview 时退化为浏览器模式,至少能用
        print(f"未加载原生窗口组件({exc}),改用浏览器打开:{url}")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            service.shutdown()
            server.shutdown()
        return 0

    window = webview.create_window(
        APP_NAME,
        url,
        width=1200,
        height=840,
        min_size=(980, 700),
        background_color="#101114",
    )

    def on_closing():
        service.shutdown()

    try:
        window.events.closing += on_closing
        window.events.shown += _style_titlebar
    except Exception:
        pass

    webview.start(debug=os.environ.get("WL_DEBUG") == "1", private_mode=False)
    service.shutdown()
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
