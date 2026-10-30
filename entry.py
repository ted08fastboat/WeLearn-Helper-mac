# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""打包入口(PyInstaller 用)。窗口模式下 stdout/stderr 为 None,先兜底再启动。"""
import io
import sys


def _ensure_streams() -> None:
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()


if __name__ == "__main__":
    _ensure_streams()
    from wlmac.app import main
    sys.exit(main())
