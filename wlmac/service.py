# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""服务层:管理登录会话、后台任务线程与日志队列,对界面暴露一份可轮询的状态快照。

线程模型:
  - 所有耗时操作(登录、拉课程、拉单元、拉小节、跑任务)都进同一把"单任务槽位";
  - 同一时刻只允许一个后台作业,避免出现两个 run() 抢同一个 Session;
  - 状态变更都在 self._lock 内完成,界面只读快照。
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from . import net, prefs
from .accuracy import AccuracyTask
from .duration import DurationTask
from .errors import LoginError, Stopped, WeLearnError

MODES = ("accuracy", "time")
MODE_NAMES = {"accuracy": "刷完成度与正确率", "time": "刷学习时长"}

STAGE_TEXT = {
    "idle": "待命",
    "login": "登录中…",
    "courses": "加载课程…",
    "units": "加载单元…",
    "sections": "加载小节…",
    "running": "任务运行中",
    "stopping": "正在停止…",
}


class Service:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.stop_event = threading.Event()
        self._job: Optional[threading.Thread] = None
        self.task: Optional[Any] = None
        self.mode = "accuracy"
        self.username = ""
        self.password = ""
        self.courses: List[dict] = []
        self.units: List[dict] = []
        self.active_cid: Optional[Any] = None
        self.sections: Dict[int, List[dict]] = {}
        self.stage = "idle"
        self.running = False
        self.result: Optional[dict] = None
        self.logs: Deque[Tuple[int, str, str]] = deque(maxlen=5000)
        self._seq = 0
        self.notice: Optional[Dict[str, Any]] = None
        self._notice_seq = 0
        self.result_text: List[str] = []
        self._shutdown = False

    # ------------------------------------------------------------------ 基础设施
    def log(self, msg: str) -> None:
        with self._lock:
            self._seq += 1
            self.logs.append((self._seq, time.strftime("%H:%M:%S"), str(msg)))

    def notice(self, level: str, text: str) -> None:
        with self._lock:
            self._notice_seq += 1
            self.notice = {"level": level, "text": text, "seq": self._notice_seq}
        self.log(text)

    def _set_stage(self, stage: str) -> None:
        with self._lock:
            self.stage = stage

    @property
    def stage_text(self) -> str:
        with self._lock:
            return STAGE_TEXT.get(self.stage, "待命")

    def busy(self) -> bool:
        with self._lock:
            return self._job is not None and self._job.is_alive()

    def _spawn(self, stage: str, fn: Callable[[], None], *, exclusive: bool = True) -> bool:
        """占用单任务槽位并启动后台线程;已被占用返回 False。"""
        with self._lock:
            if exclusive and self._job is not None and self._job.is_alive():
                return False
            self.stop_event.clear()
            self.stage = stage
            self.running = stage == "running"
            job = threading.Thread(target=self._run_job, args=(fn,), daemon=True,
                                   name=f"wl-{stage}")
            self._job = job
        job.start()
        return True

    def _run_job(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Stopped:
            self.log("已停止")
        except (WeLearnError, LoginError) as exc:
            self.notice("error", str(exc))
        except Exception as exc:  # 兜底:不让线程静默崩掉,界面至少能看到原因
            self.log(traceback.format_exc().strip().splitlines()[-1])
            self.notice("error", f"未预期的错误:{exc!r}")
        finally:
            with self._lock:
                self.running = False
                self.stage = "idle"
                self._job = None

    # ------------------------------------------------------------------ 登录 / 会话
    def login(self, username: str, password: str, mode: str = "accuracy") -> Dict[str, Any]:
        username = (username or "").strip()
        if mode not in MODES:
            return {"ok": False, "error": "未知的运行模式"}
        if not username or not password:
            return {"ok": False, "error": "请输入账号和密码"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}

        self.logout(silent=True)

        def job() -> None:
            cls = AccuracyTask if mode == "accuracy" else DurationTask
            task = cls(username, password, on_log=self.log, stop_event=self.stop_event)
            try:
                task.login()
                courses = task.fetch_courses()
            except Exception:
                task.close()
                raise
            with self._lock:
                self.task = task
                self.mode = mode
                self.username = username
                self.password = password
                self.courses = courses
                self.units = []
                self.sections = {}
                self.active_cid = None
                self.result = None
                self.result_text = []
            self.log(f"共 {len(courses)} 门课程,请选择要处理的课程")

        if not self._spawn("login", job):
            return {"ok": False, "error": "任务正在进行,请先停止"}
        return {"ok": True}

    def logout(self, silent: bool = False) -> None:
        if self.busy():
            self.stop_event.set()
            thread = self._job
            if thread is not None:
                thread.join(timeout=6)
        with self._lock:
            old = self.task
            self.task = None
            self.username = ""
            self.password = ""
            self.courses = []
            self.units = []
            self.sections = {}
            self.active_cid = None
            self.result = None
            self.result_text = []
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        if not silent:
            self.log("已退出登录")

    def set_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in MODES:
            return {"ok": False, "error": "未知的运行模式"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}
        with self._lock:
            if self.mode == mode:
                return {"ok": True}
            old = self.task
            if old is None:
                self.mode = mode
            else:
                # 复用已登录的会话与课程上下文,切模式不需要重新登录
                cls = AccuracyTask if mode == "accuracy" else DurationTask
                task = cls(old.username, old.password, on_log=self.log,
                           stop_event=self.stop_event, session=old.session)
                for attr in ("cid", "uid", "classid"):
                    setattr(task, attr, getattr(old, attr, ""))
                task.units = list(getattr(old, "units", []) or [])
                self.task = task
                self.mode = mode
                self.result = None
                self.result_text = []
        self.log(f"已切换到「{MODE_NAMES[mode]}」")
        return {"ok": True}

    # ------------------------------------------------------------------ 数据加载
    def refresh_courses(self) -> Dict[str, Any]:
        if self.task is None:
            return {"ok": False, "error": "请先登录"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}

        def job() -> None:
            courses = self.task.fetch_courses()
            with self._lock:
                self.courses = courses
            self.log(f"已刷新,共 {len(courses)} 门课程")

        if not self._spawn("courses", job):
            return {"ok": False, "error": "任务正在进行,请先停止"}
        return {"ok": True}

    def select_course(self, cid: Any) -> Dict[str, Any]:
        if self.task is None:
            return {"ok": False, "error": "请先登录"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}
        if cid in (None, ""):
            return {"ok": False, "error": "请选择课程"}

        def job() -> None:
            units = self.task.fetch_units(cid)
            with self._lock:
                self.active_cid = cid
                self.units = units
                self.sections = {}
            self.log(f"已加载 {len(units)} 个单元")

        if not self._spawn("units", job):
            return {"ok": False, "error": "任务正在进行,请先停止"}
        return {"ok": True}

    @staticmethod
    def _map_sections(raw: List[dict]) -> List[dict]:
        return [{"location": x.get("location", f"小节 {i + 1}"),
                 "complete": "未" not in x.get("iscomplete", "未"),
                 "visible": x.get("isvisible", "true") != "false"}
                for i, x in enumerate(raw)]

    def load_sections(self, unit_no: int) -> Dict[str, Any]:
        if self.task is None:
            return {"ok": False, "error": "请先登录"}
        if not self.units:
            return {"ok": False, "error": "请先选择课程"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}
        if not 1 <= unit_no <= len(self.units):
            return {"ok": False, "error": f"单元编号需在 1~{len(self.units)} 之间"}
        with self._lock:
            cached = self.sections.get(unit_no)
        if cached is not None:
            return {"ok": True, "cached": True}

        def job() -> None:
            items = self._map_sections(self.task.fetch_sections(unit_no))
            with self._lock:
                self.sections[unit_no] = items
            self.log(f"单元 {unit_no} 共 {len(items)} 个小节")

        if not self._spawn("sections", job):
            return {"ok": False, "error": "任务正在进行,请先停止"}
        return {"ok": True}

    def _ensure_sections(self, unit_no: int) -> Optional[List[dict]]:
        """启动前确保已知该单元的小节数量,用于校验小节编号是否越界。"""
        with self._lock:
            cached = self.sections.get(unit_no)
        if cached is not None:
            return cached
        try:
            items = self._map_sections(self.task.fetch_sections(unit_no))
        except WeLearnError as exc:
            self.log(f"小节预检失败(单元 {unit_no}):{exc}")
            return None
        with self._lock:
            self.sections[unit_no] = items
        return items

    # ------------------------------------------------------------------ 运行任务
    def start(self, units_payload: Any, sections_payload: Any, param_text: str) -> Dict[str, Any]:
        if self.task is None:
            return {"ok": False, "error": "请先登录"}
        if not self.units:
            return {"ok": False, "error": "请先选择课程"}
        if self.busy():
            return {"ok": False, "error": "任务正在进行,请先停止"}

        try:
            all_units, unit_list, section_map = net.normalize_targets(units_payload,
                                                                      sections_payload)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        if section_map:
            for unit_no, secs in section_map.items():
                items = self._ensure_sections(unit_no)
                if items is not None and max(secs) > len(items):
                    return {"ok": False,
                            "error": f"单元 {unit_no} 只有 {len(items)} 个小节,编号超出范围"}

        try:
            param = net.parse_numeric_param(param_text)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        if self.mode == "time" and isinstance(param, tuple) and param[1] > 3600:
            return {"ok": False, "error": "单个小节增加时长不应超过 3600 秒"}

        desc = "全部单元" if all_units else "单元 " + ",".join(str(u) for u in unit_list or [])
        if section_map:
            desc += " 的指定小节"
        mode = self.mode
        task = self.task

        def job() -> None:
            self.log(f"开始任务:{MODE_NAMES[mode]} · {desc} · 参数 {param}")
            result = task.run(0 if all_units else list(unit_list or []), param, section_map)
            lines = self._format_result(mode, result)
            with self._lock:
                self.result = result
                self.result_text = lines
            for line in lines:
                self.log(line)

        if not self._spawn("running", job):
            return {"ok": False, "error": "任务正在进行,请先停止"}
        return {"ok": True}

    @staticmethod
    def _format_result(mode: str, result: dict) -> List[str]:
        if mode == "time":
            lines = [f"本次共 {result.get('total', 0)} 个小节,"
                     f"成功 {result.get('succeed', 0)},失败 {result.get('failed', 0)}"]
            for i, err in enumerate(result.get("errors", []), start=1):
                lines.append(f"  第 {i} 个失败:{err}")
            return lines
        return [f"方式1(整段 cmi):{result.get('way1_succeed', 0)} 成功 / "
                f"{result.get('way1_failed', 0)} 失败",
                f"方式2(进度回写):{result.get('way2_succeed', 0)} 成功 / "
                f"{result.get('way2_failed', 0)} 失败"]

    def stop(self) -> Dict[str, Any]:
        if not self.busy():
            return {"ok": False, "error": "当前没有正在执行的操作"}
        self.stop_event.set()
        with self._lock:
            if self.stage == "running":
                self.stage = "stopping"
        self.log("已请求停止,等待当前小节收尾…")
        return {"ok": True}

    # ------------------------------------------------------------------ 快照
    def snapshot(self, after: int = 0) -> Dict[str, Any]:
        with self._lock:
            logs = [list(entry) for entry in self.logs if entry[0] > after]
            units = [{"no": i, "unitname": u.get("unitname", ""), "name": u.get("name", ""),
                      "visible": u.get("visible", "true") == "true"}
                     for i, u in enumerate(self.units, start=1)]
            courses = [{"cid": c.get("cid"), "name": c.get("name", ""),
                        "per": c.get("per", 0)} for c in self.courses]
            return {
                "stage": self.stage,
                "stage_text": self.stage_text,
                "busy": self.busy(),
                "running": self.running,
                "has_task": self.task is not None,
                "mode": self.mode,
                "username": self.username,
                "courses": courses,
                "units": units,
                "active_cid": self.active_cid,
                "sections": {str(k): v for k, v in self.sections.items()},
                "result_text": list(self.result_text),
                "logs": logs,
                "seq": self._seq,
                "notice": self.notice,
            }

    def shutdown(self) -> None:
        self._shutdown = True
        try:
            self.stop_event.set()
        except Exception:
            pass
        with self._lock:
            task = self.task
        if task is not None:
            try:
                task.close()
            except Exception:
                pass


service = Service()  # 单进程单实例,web 与 app 共用
