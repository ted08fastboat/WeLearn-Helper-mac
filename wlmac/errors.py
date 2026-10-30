# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""统一异常层次:业务层抛出,界面层只负责把 str(e) 展示给用户。"""


class WeLearnError(Exception):
    """业务流程异常(响应异常、无课程、网络失败等),消息可直接展示给用户。"""


class LoginError(WeLearnError):
    """账号密码错误或登录流程失败。"""


class Stopped(WeLearnError):
    """用户请求停止。"""

    def __init__(self, msg: str = "已停止"):
        super().__init__(msg)
