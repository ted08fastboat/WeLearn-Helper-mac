# 本文件本仓库新增。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""界面预览夹具(仅开发用):灌入假数据起一个本地服务,方便截图/走查布局。

    python tools/preview_ui.py 17800
    浏览器打开 http://127.0.0.1:17800/?theme=light 可切换配色
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.serving import make_server

from wlmac.service import Service
from wlmac.web import create_app

COURSES = [
    {"cid": 101, "per": 73, "name": "大学英语视听说（三）"},
    {"cid": 102, "per": 100, "name": "学术英语写作"},
    {"cid": 103, "per": 12, "name": "跨文化交际导论"},
    {"cid": 104, "per": 55, "name": "英语国家社会与文化"},
]

UNITS = [{"unitname": f"Unit {i}", "name": name, "visible": vis}
         for i, (name, vis) in enumerate([
             ("College Life", "true"), ("Cultural Differences", "true"),
             ("Technology Today", "true"), ("Environment", "true"),
             ("Future Career", "false"), ("Review", "true"),
         ], start=1)]

SECTIONS = [
    {"location": f"2.{i} {title}", "complete": done, "visible": True}
    for i, (title, done) in enumerate([
        ("Lead-in", True), ("Listening", True), ("Speaking", False),
        ("Reading", False), ("Vocabulary", False), ("Grammar", False),
        ("Writing", False), ("Translation", False), ("Culture Link", False),
        ("Unit Test", False),
    ], start=1)
]

LOGS = [
    "登录成功",
    "共 4 门课程,请选择要处理的课程",
    "已加载 6 个单元",
    "单元 2 共 10 个小节",
    "开始任务:刷完成度与正确率 · 单元 2 的指定小节 · 参数 100",
    "[已完成]  2.1 Lead-in",
    "[已完成]  2.2 Listening",
    "[提交中]  2.3 Speaking",
    "    └ 正确率 100%  方式1:成功  方式2:成功",
    "[提交中]  2.4 Reading",
    "    └ 正确率 100%  方式1:成功  方式2:成功",
    "[提交中]  2.5 Vocabulary",
    "    └ 正确率  98%  方式1:成功  方式2:失败",
    "[跳过]    2.6 Grammar (未开放)",
    "[!] 单元 5 内没有匹配的小节编号,已跳过",
    "方式1(整段 cmi):3 成功 / 0 失败",
    "方式2(进度回写):2 成功 / 1 失败",
]


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 17800
    svc = Service()
    svc.task = object()               # 只用于 has_task 判定
    svc.username = "2024110886"
    svc.mode = "accuracy"
    svc.courses = COURSES
    svc.units = UNITS
    svc.active_cid = 101
    svc.sections = {2: SECTIONS}
    svc.result_text = ["方式1(整段 cmi):3 成功 / 0 失败",
                       "方式2(进度回写):2 成功 / 1 失败"]
    for line in LOGS:
        svc.log(line)

    server = make_server("127.0.0.1", port, create_app(svc), threaded=True)
    print(f"preview on http://127.0.0.1:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    time.sleep(0)
    sys.exit(main())
