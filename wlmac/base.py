# 本文件移植自 YZBRH/Welearn_helper 的逆向实现。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""两个任务引擎共用的会话/课程上下文基类。"""
from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional

from . import net
from .errors import Stopped


def _default_log(msg: str) -> None:
    print(msg, flush=True)


class BaseTask:
    """持有登录会话与课程上下文;run() 由子类实现。所有输出走 on_log 回调。"""

    def __init__(self, username: str, password: str,
                 on_log: Optional[Callable[[str], None]] = None,
                 stop_event: Optional[threading.Event] = None,
                 session: Optional[Any] = None):
        self.username = username
        self.password = password
        self.on_log = on_log or _default_log
        self.stop_event = stop_event or threading.Event()
        self.session = session or net.new_session(self.on_log)
        self.cid = ""
        self.uid = ""
        self.classid = ""
        self.units: List[Any] = []

    # --- 生命周期 -------------------------------------------------------
    def _stopped(self) -> bool:
        return self.stop_event.is_set()

    def _check_stop(self) -> None:
        if self._stopped():
            raise Stopped()

    def login(self) -> None:
        net.login(self.session, self.username, self.password,
                  on_log=self.on_log, stop_event=self.stop_event)

    def fetch_courses(self) -> List[dict]:
        return net.fetch_courses(self.session)

    def fetch_units(self, cid: Any) -> List[dict]:
        self.cid = str(cid)
        self.uid, self.classid = net.get_course_ids(self.session, self.cid)
        self.units = net.fetch_units(self.session, self.cid, self.uid)
        return self.units

    def fetch_sections(self, unit_index: int) -> List[dict]:
        """unit_index 为 1-based 展示编号。"""
        return net.fetch_sections(self.session, self.cid, self.uid,
                                  unit_index - 1, self.classid)

    def close(self) -> None:
        net.close_session(self.session)
