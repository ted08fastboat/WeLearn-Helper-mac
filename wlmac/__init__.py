# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""WeLearn Helper for macOS —— 基于 WeLearn_helper 逆向结果重写的 macOS 原生版本。

上游协议参考:https://github.com/YZBRH/Welearn_helper (原作者 Avenshy,维护者 YZBRH / lxbsdsg)
本包仅保留"协议层 + 任务引擎"作为可复用核心,界面与运行方式针对 macOS 重写。
"""

__version__ = "1.0.0"
APP_NAME = "WeLearn Helper"
BUNDLE_ID = "com.github.welearnhelper.mac"
KEYCHAIN_SERVICE = "WeLearnHelper"

# 上游项目与作者,界面上展示,避免抹掉来源
UPSTREAM_REPO = "https://github.com/YZBRH/Welearn_helper"
ORIGINAL_AUTHOR = "Avenshy / SSmJaE"
