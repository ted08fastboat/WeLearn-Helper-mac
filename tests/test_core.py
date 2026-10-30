# 本文件本仓库新增。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""核心回归测试:密文算法、参数解析、两个引擎的请求序列、服务层 API。

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 隔离配置目录,避免测试污染 ~/Library/Application Support/WeLearnHelper
os.environ["WL_CONFIG_DIR"] = tempfile.mkdtemp(prefix="wl-test-")

from wlmac import net  # noqa: E402
from wlmac.accuracy import AccuracyTask  # noqa: E402
from wlmac.duration import DurationTask  # noqa: E402
from wlmac.service import Service  # noqa: E402
from wlmac.web import create_app  # noqa: E402


class FakeResponse:
    def __init__(self, json_data=None, text=""):
        self._json = json_data
        self.text = text
        self.status_code = 200
        self.headers = {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    """记录调用并按 URL/action 路由返回,替代 tls_client.Session。"""

    def __init__(self, routes):
        self.routes = routes          # [(needle, FakeResponse 或 callable), ...]
        self.calls = []               # [(method, url, data)]

    def _call(self, method, url, **kwargs):
        data = kwargs.get("data") or {}
        self.calls.append((method, url, data))
        haystack = url + "|" + str(data.get("action", ""))
        for needle, resp in self.routes:
            if needle in haystack:
                return resp(data) if callable(resp) else resp
        raise AssertionError(f"未预置响应:{method} {url} {data}")

    def close(self):
        pass

    def actions(self):
        return [c[2].get("action") for c in self.calls if c[2]]


SCO_INFO = {
    "info": [
        {"location": "1.1 Listening", "iscomplete": "未完成", "isvisible": "true", "id": 101},
        {"location": "1.2 Reading", "iscomplete": "已完成", "isvisible": "true", "id": 102},
        {"location": "1.3 Extra", "iscomplete": "未完成", "isvisible": "false", "id": 103},
    ]
}


class TestCipher(unittest.TestCase):
    # 期望值由上游 common.js 在同一时间戳下计算得出
    VECTORS = [
        ("abc123", 1761832718345, "MTc2MTgzMjcxODM1Nyo2MTYyNjMzMTMyMzM=", 1761832718357),
        ("密码测试123", 1761832718345,
         "MTc2MTgzMjcxODM4OSplNWFmODZlN2EwODFlNmI1OGJlOGFmOTUzMTMyMzM=", 1761832718389),
    ]

    def test_matches_browser_js(self):
        for pwd, now, expect_cipher, expect_ts in self.VECTORS:
            cipher, ts = net.generate_cipher_text(pwd, now_ms=now)
            self.assertEqual(cipher, expect_cipher)
            self.assertEqual(ts, expect_ts)

    def test_timestamp_invariant(self):
        pwd = "P@ssw0rd!"
        for now in (1_600_000_000_000, 1_761_832_718_345, 1_899_999_999_999):
            _, ts = net.generate_cipher_text(pwd, now_ms=now)
            checksum = ((now >> 16) & 0xFF)
            for byte in pwd.encode():
                checksum ^= byte
            self.assertEqual(ts % 100, checksum % 100)
            self.assertLessEqual(now - ts, 100)


class TestParams(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(net.parse_numeric_param("30"), 30)
        self.assertEqual(net.parse_numeric_param(" 70,100 "), (70, 100))
        for bad in ("", "abc", "10,20,30", "90,80", "-5", "1.5"):
            with self.assertRaises(ValueError):
                net.parse_numeric_param(bad)

    def test_targets(self):
        self.assertEqual(net.normalize_targets(0), (True, None, None))
        self.assertEqual(net.normalize_targets([3, 1, 3]), (False, [1, 3], None))
        self.assertEqual(net.normalize_targets(2, {2: [1, 2]})[2], {2: [1, 2]})
        with self.assertRaises(ValueError):
            net.normalize_targets("12")
        with self.assertRaises(ValueError):
            net.normalize_targets(0, {1: [1]})
        with self.assertRaises(ValueError):
            net.normalize_targets(1, {2: [1]})


class TestAccuracyEngine(unittest.TestCase):
    def test_unit_flow(self):
        # 「全部单元」模式靠服务端报错停下:unitidx=0 有数据,其余一律回异常文本
        session = FakeSession([
            ("courseunits", FakeResponse(json_data=SCO_INFO)),
            ("scoLeaves", FakeResponse(json_data=SCO_INFO)),
            ("setscoinfo", FakeResponse(text='{"ret":0}')),
            ("savescoinfo", FakeResponse(text='{"ret":0}')),
            ("startsco", FakeResponse(text="")),
        ])
        original = session._call

        def call(method, url, **kwargs):
            if "scoLeaves" in url or "StudyStat" in url:
                if "unitidx=0" not in url:
                    session.calls.append((method, url, kwargs.get("data") or {}))
                    return FakeResponse(text="出错了")
            return original(method, url, **kwargs)

        session._call = call
        task = AccuracyTask("u", "p", session=session)
        task.cid, task.uid, task.classid = "11", "22", "33"

        logs = []
        task.on_log = logs.append
        result = task.run(0, 100)

        self.assertEqual(result["way1_succeed"], 1)
        self.assertEqual(result["way1_failed"], 0)
        self.assertEqual(result["way2_succeed"], 1)
        self.assertEqual(result["submitted"], 1)      # 已完成与未开放的小节被跳过
        actions = session.actions()
        self.assertIn("startsco160928", actions)
        self.assertIn("setscoinfo", actions)
        self.assertIn("savescoinfo160928", actions)
        payload = [c[2] for c in session.calls if c[2].get("action") == "setscoinfo"][0]
        self.assertIn('"scaled":"100"', payload["data"])
        self.assertTrue(any("已完成" in line for line in logs))

    def test_section_filter(self):
        session = FakeSession([
            ("scoLeaves", FakeResponse(json_data=SCO_INFO)),
            ("setscoinfo", FakeResponse(text='{"ret":0}')),
            ("savescoinfo", FakeResponse(text='{"ret":0}')),
            ("startsco", FakeResponse(text="")),
        ])
        task = AccuracyTask("u", "p", session=session)
        task.cid, task.uid, task.classid = "11", "22", "33"
        result = task.run([1], (80, 90), {1: [2]})
        self.assertEqual(result["submitted"], 0)       # 只勾了已完成小节 → 不提交
        self.assertEqual(result["sections_hit"], 1)


class TestDurationEngine(unittest.TestCase):
    def test_heartbeat_flow(self):
        cmi = json.dumps({"cmi": {"score": {"scaled": "88"}, "completion_status": "incomplete",
                                  "progress_measure": "0.4", "total_time": "120",
                                  "session_time": "120"}})
        session = FakeSession([
            ("scoLeaves", FakeResponse(json_data=SCO_INFO)),
            ("getscoinfo_v7", FakeResponse(json_data={"comment": cmi})),
            ("keepsco", FakeResponse(text="ok")),
            ("savescoinfo", FakeResponse(text="ok")),
        ])
        task = DurationTask("u", "p", session=session)
        task.cid, task.uid, task.classid = "11", "22", "33"
        task.request_interval = 0
        result = task.run([1], 1, {1: [1]})

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["failed"], 0)
        actions = session.actions()
        self.assertIn("getscoinfo_v7", actions)
        self.assertIn("keepsco_with_getticket_with_updatecmitime", actions)
        save = [c[2] for c in session.calls if c[2].get("action") == "savescoinfo160928"][0]
        self.assertEqual(save["crate"], "88")
        self.assertEqual(save["cstatus"], "incomplete")


class TestServiceApi(unittest.TestCase):
    def setUp(self):
        self.original = (net.new_session, net.login, net.fetch_courses,
                         net.get_course_ids, net.fetch_units)
        session = FakeSession([
            ("scoLeaves", FakeResponse(json_data=SCO_INFO)),
            ("setscoinfo", FakeResponse(text='{"ret":0}')),
            ("savescoinfo", FakeResponse(text='{"ret":0}')),
            ("startsco", FakeResponse(text="")),
        ])
        net.new_session = lambda on_log=None: session
        net.login = lambda *a, **k: None
        net.fetch_courses = lambda s: [{"cid": 11, "per": 60, "name": "课程A"}]
        net.get_course_ids = lambda s, cid: ("22", "33")
        net.fetch_units = lambda s, cid, uid: [
            {"unitname": "Unit 1", "name": "第一单元", "visible": "true"}]
        self.session = session
        self.service = Service()
        self.client = create_app(self.service).test_client()

    def tearDown(self):
        net.new_session, net.login, net.fetch_courses, net.get_course_ids, net.fetch_units = self.original

    def _wait(self, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.service.busy():
                return
            time.sleep(0.02)
        self.fail("后台作业超时")

    def test_full_flow(self):
        self.assertEqual(self.client.get("/api/state").get_json()["ok"], True)

        res = self.client.post("/api/login", json={"username": "u", "password": "p",
                                                   "mode": "accuracy"}).get_json()
        self.assertTrue(res["ok"])
        self._wait()
        snap = self.client.get("/api/state").get_json()
        self.assertTrue(snap["has_task"])
        self.assertEqual(snap["courses"][0]["name"], "课程A")

        self.client.post("/api/course", json={"cid": 11})
        self._wait()
        snap = self.client.get("/api/state").get_json()
        self.assertEqual(len(snap["units"]), 1)

        self.client.post("/api/sections", json={"unit": 1})
        self._wait()
        snap = self.client.get("/api/state").get_json()
        self.assertEqual(len(snap["sections"]["1"]), 3)
        self.assertFalse(snap["sections"]["1"][0]["complete"])

        started = self.client.post("/api/start", json={"units": 1, "sections": None,
                                                       "param": "100"}).get_json()
        self.assertTrue(started["ok"])
        self._wait()
        snap = self.client.get("/api/state").get_json()
        self.assertTrue(any("方式1" in line for line in snap["result_text"]))
        self.assertFalse(snap["running"])

    def test_rejects_bad_param(self):
        self.client.post("/api/login", json={"username": "u", "password": "p"})
        self._wait()
        self.client.post("/api/course", json={"cid": 11})
        self._wait()
        res = self.client.post("/api/start", json={"units": 1, "param": "abc"}).get_json()
        self.assertFalse(res["ok"])
        res = self.client.post("/api/start", json={"units": 1, "sections": {1: [9]},
                                                   "param": "100"}).get_json()
        self.assertFalse(res["ok"])            # 小节编号越界

    def test_static_assets_served(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/assets/style.css").status_code, 200)
        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
