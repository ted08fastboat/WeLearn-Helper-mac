# 本文件移植自 YZBRH/Welearn_helper 的逆向实现。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""刷完成度 / 刷正确率引擎(对应上游 welearn_accuracy.py)。

协议要点:SCO 的完成状态是用两个接口一起"写"出来的 ——
  setscoinfo    提交整段 cmi JSON(completion_status=completed, score.scaled=正确率)
  savescoinfo   再提交一次进度汇总(progress=100, cstatus=completed, crate=正确率)
两个接口都回 "ret":0 才算成功,上游也是分开计数的,这里保留该口径。
"""
from __future__ import annotations

from random import randint
from typing import Any, Dict, List, Optional

from . import net
from .base import BaseTask
from .errors import WeLearnError

MAX_UNITS = 200   # 「全部单元」模式下的推进上限,防止接口异常返回导致死循环

SCO_DATA_TEMPLATE = (
    '{"cmi":{"completion_status":"completed","interactions":[],"launch_data":"",'
    '"progress_measure":"1","score":{"scaled":"{crate}","raw":"100"},'
    '"session_time":"0","success_status":"unknown","total_time":"0","mode":"normal"},'
    '"adl":{"data":[]},"cci":{"data":[],"service":{"dictionary":{"headword":"",'
    '"short_cuts":""},"new_words":[],"notes":[],"writing_marking":[],"record":'
    '{"files":[]},"play":{"offline_media_id":"9999"}},"retry_count":"0",'
    '"submit_time":""}}[INTERACTIONINFO]'
)


class AccuracyTask(BaseTask):
    """刷完成度与正确率。units=0 表示全部单元(沿用上游"探测到报错即停"的做法)。"""

    def run(self, units, param, sections=None) -> Dict[str, Any]:
        all_units, unit_list, section_map = net.normalize_targets(units, sections)
        random_mode = isinstance(param, tuple)

        stats = {"way1_succeed": 0, "way1_failed": 0,
                 "way2_succeed": 0, "way2_failed": 0,
                 "sections_hit": 0, "submitted": 0}

        info_headers = {
            "Referer": f"{net.AJAX_BASE}/2019/student/course_info.aspx?cid={self.cid}",
        }

        def process_unit(unit_idx: int, unit_no: int) -> bool:
            """处理一个单元。unit_idx 为 0-based 接口参数,unit_no 为 1-based 展示编号。
            返回 False 表示服务器报错(单元不存在 / 已到末尾)。"""
            response = self.session._call(
                "get",
                f"{net.UNITS_URL}?action=scoLeaves&cid={self.cid}&uid={self.uid}"
                f"&unitidx={unit_idx}&classid={self.classid}",
                headers=info_headers,
            )
            text = response.text or ""
            if "异常" in text or "出错了" in text:
                return False
            try:
                courses = response.json()["info"]
            except Exception:
                return False

            wanted = section_map.get(unit_no) if section_map else None
            hit_in_unit = False
            for no, course in enumerate(courses, start=1):
                self._check_stop()
                if wanted and no not in wanted:
                    continue
                if wanted:
                    stats["sections_hit"] += 1
                    hit_in_unit = True

                location = course.get("location", "")
                if course.get("isvisible") == "false":
                    self.on_log(f"[跳过]    {location} (未开放)")
                    continue
                if "未" not in course.get("iscomplete", "未"):
                    self.on_log(f"[已完成]  {location}")
                    continue

                self.on_log(f"[提交中]  {location}")
                crate = str(randint(param[0], param[1])) if random_mode else str(param)
                sco_headers = {
                    "Referer": f"{net.AJAX_BASE}/Student/StudyCourse.aspx"
                               f"?cid={self.cid}&classid={self.classid}&sco={course.get('id')}",
                }
                base_data = {"cid": self.cid, "scoid": course.get("id"), "uid": self.uid}

                try:
                    self.session._call("post", net.SCO_AJAX_URL,
                                       data={**base_data, "action": "startsco160928"},
                                       headers=sco_headers)
                    resp1 = self.session._call(
                        "post", net.SCO_AJAX_URL,
                        data={**base_data, "action": "setscoinfo",
                              "data": SCO_DATA_TEMPLATE.replace("{crate}", crate),
                              "isend": "False"},
                        headers=sco_headers)
                    way1_ok = '"ret":0' in (resp1.text or "")
                    stats["way1_succeed" if way1_ok else "way1_failed"] += 1

                    resp2 = self.session._call(
                        "post", net.SCO_AJAX_URL,
                        data={**base_data, "action": "savescoinfo160928",
                              "progress": "100", "crate": crate,
                              "status": "unknown", "cstatus": "completed",
                              "trycount": "0"},
                        headers=sco_headers)
                    way2_ok = '"ret":0' in (resp2.text or "")
                    stats["way2_succeed" if way2_ok else "way2_failed"] += 1
                except WeLearnError as exc:
                    stats["way1_failed"] += 1
                    stats["way2_failed"] += 1
                    self.on_log(f"[网络错误] {location} → {exc}")
                    continue

                self.on_log(f"    └ 正确率 {crate:>3}%  方式1:{'成功' if way1_ok else '失败'}"
                            f"  方式2:{'成功' if way2_ok else '失败'}")
                stats["submitted"] += 1

            if wanted and not hit_in_unit:
                self.on_log(f"[!] 单元 {unit_no} 内没有匹配的小节编号,已跳过")
            return True

        if all_units:
            unit_idx = 0
            while True:
                self._check_stop()
                if unit_idx >= MAX_UNITS:
                    # 防御:若服务端对任意 unitidx 都返回数据,原版"探测到报错才停"会死循环
                    self.on_log(f"已处理 {MAX_UNITS} 个单元,达到上限,停止推进")
                    break
                if not process_unit(unit_idx, unit_idx + 1):
                    self.on_log(f"单元 {unit_idx + 1} 不可用,全部单元处理完毕")
                    break
                unit_idx += 1
        else:
            for unit_no in unit_list or []:
                self._check_stop()
                if not process_unit(unit_no - 1, unit_no):
                    self.on_log(f"[!] 单元 {unit_no} 不可用,已跳过")

        if section_map and stats["sections_hit"] == 0:
            self.on_log("[!] 没有命中任何指定小节,请检查小节编号是否超出范围")
        return stats
