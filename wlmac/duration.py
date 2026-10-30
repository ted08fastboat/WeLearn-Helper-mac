# 本文件移植自 YZBRH/Welearn_helper 的逆向实现。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""刷学习时长引擎(对应上游 welearn_time.py)。

协议要点:
1. getscoinfo_v7 拿到该 SCO 当前的 cmi(session_time / total_time / 正确率快照),
   若回 "学习数据不正确" 需先 startsco160928 再取一次。
2. keepsco_with_getticket_with_updatecmitime 作为心跳,每 60 秒补一次,
   服务端按"会话存活时长"累计学习时间,这是刷时长能被记上的关键。
3. 最后 savescoinfo160928 回写快照(沿用服务端给的原值,不自造)。

macOS 版改动:上游用 asyncio.gather 并发跑所有小节,但多个协程共用同一个
tls_client Session 并非线程安全,这里用一把 asyncio.Lock 串行化网络请求 ——
"等待时长"仍然是并行的,只有几毫秒级的 HTTP 调用被排队,行为不变但大幅降噪。
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from . import net
from .base import BaseTask
from .errors import Stopped, WeLearnError

REQUEST_INTERVAL = 2      # 每个动作前的等待秒数(与上游一致)
HEARTBEAT_INTERVAL = 1
AJAX_URL = net.SCO_AJAX_URL


class DurationTask(BaseTask):
    """给每个小节累计指定秒数的学习时长。param 为 int 或 (lo, hi) 区间。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_interval = REQUEST_INTERVAL

    def _pick(self, target) -> int:
        if isinstance(target, tuple):
            return random.randint(target[0], target[1])
        return int(target)

    def run(self, units, param, sections=None) -> Dict[str, Any]:
        all_units, unit_list, section_map = net.normalize_targets(units, sections)
        errors: List[str] = []
        pending: List[Tuple[int, dict]] = []

        indices = range(len(self.units)) if all_units else [(u - 1) for u in (unit_list or [])]
        for idx, unit_idx in enumerate(indices, start=1):
            self._check_stop()
            self.on_log(f"读取单元 {unit_idx + 1} 的小节…")
            try:
                chapters = net.fetch_sections(self.session, self.cid, self.uid,
                                              unit_idx, self.classid)
            except WeLearnError as exc:
                self.on_log(f"[!] 单元 {unit_idx + 1} 读取失败:{exc}")
                continue
            wanted = section_map.get(unit_idx + 1) if section_map else None
            for no, chapter in enumerate(chapters, start=1):
                if wanted and no not in wanted:
                    continue
                pending.append((self._pick(param), chapter))

        if not pending:
            self.on_log("[!] 没有需要处理的小节")
            return {"total": 0, "succeed": 0, "failed": 0, "errors": []}

        self.on_log(f"共 {len(pending)} 个小节,开始累计学习时长…")
        asyncio.run(self._run_all(pending, errors))

        succeed = len(pending) - len(errors)
        return {"total": len(pending), "succeed": succeed,
                "failed": len(errors), "errors": list(errors)}

    async def _run_all(self, pending: List[Tuple[int, dict]], errors: List[str]) -> None:
        lock = asyncio.Lock()
        max_time = max(t for t, _ in pending)
        chapters = [asyncio.ensure_future(self._simulate(learning_time, chapter, errors, lock))
                    for learning_time, chapter in pending]
        heartbeat = asyncio.ensure_future(self._heartbeat(chapters, max_time))
        try:
            await asyncio.gather(*chapters, return_exceptions=True)
        finally:
            # 小节全部结束就立刻收尾;否则心跳会把 run() 拖到"预计时长"走完
            heartbeat.cancel()

    async def _simulate(self, learning_time: int, chapter: dict,
                        errors: List[str], lock: asyncio.Lock) -> None:
        location = chapter.get("location", "")
        try:
            await self._simulate_inner(learning_time, chapter, lock)
        except Stopped:
            self.on_log(f"[停止] 已跳过剩余时长:{location}")
        except WeLearnError as exc:
            self.on_log(f"[错误] {location} → {exc}")
            errors.append(location)
        except Exception as exc:  # 单节失败不应拖垮整批
            self.on_log(f"[错误] {location} → {exc!r}")
            errors.append(location)

    async def _simulate_inner(self, learning_time: int, chapter: dict,
                              lock: asyncio.Lock) -> None:
        location = chapter.get("location", "")
        self.on_log(f"章节 {location}  已学 {chapter.get('learntime', '0')}  计划 +{learning_time}s")

        common_headers = {"Referer": f"{net.AJAX_BASE}/student/StudyCourse.aspx"}
        common = {"uid": self.uid, "cid": self.cid, "scoid": chapter.get("id")}

        # 等待在锁外进行(否则小节之间会互相排队等待,总时长被放大);
        # 只有真正的 HTTP 调用进锁,保证同一个 Session 不被并发使用
        await asyncio.sleep(self.request_interval)
        async with lock:
            resp = self.session._call("post", AJAX_URL,
                                      data={**common, "action": "getscoinfo_v7"},
                                      headers=common_headers)

        if "学习数据不正确" in (resp.text or ""):
            await asyncio.sleep(self.request_interval)
            async with lock:
                self.session._call("post", AJAX_URL,
                                   data={**common, "action": "startsco160928"},
                                   headers=common_headers)
                resp = self.session._call("post", AJAX_URL,
                                          data={**common, "action": "getscoinfo_v7"},
                                          headers=common_headers)
            if "学习数据不正确" in (resp.text or ""):
                raise WeLearnError("学习数据不正确(重试后仍失败)")

        try:
            payload = resp.json().get("comment", "")
        except Exception:
            payload = ""
        cmi = {}
        if payload:
            try:
                cmi = json.loads(payload).get("cmi", {})
            except Exception:
                cmi = {}
        crate = (cmi.get("score") or {}).get("scaled", "") if cmi else ""
        cstatus = cmi.get("completion_status", "not_attempted") if cmi else "not_attempted"
        progress = cmi.get("progress_measure", "0") if cmi else "0"
        total_time = cmi.get("total_time", "0") if cmi else "0"
        session_time = cmi.get("session_time", "0") if cmi else "0"

        await asyncio.sleep(self.request_interval)
        async with lock:
            self.session._call("post", AJAX_URL,
                               data={**common, "action": "keepsco_with_getticket_with_updatecmitime",
                                     "session_time": session_time, "total_time": total_time},
                               headers=common_headers)

        for current in range(1, learning_time + 1):
            self._check_stop()
            await asyncio.sleep(1)
            if current % 60 == 0:
                async with lock:
                    self.session._call("post", AJAX_URL,
                                       data={**common,
                                             "action": "keepsco_with_getticket_with_updatecmitime",
                                             "session_time": session_time,
                                             "total_time": total_time},
                                       headers=common_headers)

        self._check_stop()
        await asyncio.sleep(self.request_interval)
        async with lock:
            self.session._call("post", AJAX_URL,
                               data={**common, "action": "savescoinfo160928",
                                     "crate": crate, "cstatus": cstatus, "status": "unknown",
                                     "progress": progress, "trycount": "0"},
                               headers=common_headers)
        self.on_log(f"    └ 完成 +{learning_time}s")

    async def _heartbeat(self, chapters: List["asyncio.Future"], max_learning_time: int) -> None:
        start = time.time()
        estimate = max_learning_time + 4 * self.request_interval
        next_report = 10
        while not self._stopped():
            if all(task.done() for task in chapters):
                return
            elapsed = int(time.time() - start)
            if elapsed >= next_report:
                self.on_log(f"预计学习时长 {estimate}s,已学习 {elapsed}s")
                next_report = elapsed + 10
            await asyncio.sleep(HEARTBEAT_INTERVAL)
