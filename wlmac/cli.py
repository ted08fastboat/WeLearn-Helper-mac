# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""终端模式 —— 给习惯命令行的同学留的入口(等价于上游 main.py)。

    python -m wlmac.cli
"""
from __future__ import annotations

import getpass
import sys

from . import APP_NAME, ORIGINAL_AUTHOR, UPSTREAM_REPO, __version__
from .accuracy import AccuracyTask
from .duration import DurationTask
from .errors import LoginError, Stopped, WeLearnError
from .net import parse_numeric_param

BANNER = f"""
╭──────────────────────────────────────────────╮
│  {APP_NAME} for macOS  v{__version__}
│  协议逆向自 {UPSTREAM_REPO}
│  原作者 {ORIGINAL_AUTHOR} · GPLv3 · 禁止售卖
╰──────────────────────────────────────────────╯
"""


def _pick(prompt: str, options: int):
    while True:
        raw = input(prompt).strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            print("请输入数字")
            continue
        if 0 <= value <= options:
            return value
        print(f"请输入 0~{options} 之间的数字")


def run_flow(mode: str) -> None:
    username = input("账号:").strip()
    password = getpass.getpass("密码(输入不显示):")
    task = AccuracyTask(username, password) if mode == "accuracy" else DurationTask(username, password)
    try:
        task.login()
        courses = task.fetch_courses()
    except (LoginError, WeLearnError) as exc:
        print(f"登录失败:{exc}")
        return

    print("\n我的课程:")
    for i, course in enumerate(courses, start=1):
        print(f"  [{i:>2}] 完成度 {course.get('per', 0):>3}%  {course.get('name', '')}")
    index = _pick("\n选择课程序号:", len(courses))
    if index == 0:
        return

    units = task.fetch_units(courses[index - 1]["cid"])
    print("\n单元列表:")
    print("  [ 0] 全部单元")
    for i, unit in enumerate(units, start=1):
        flag = "已开放" if unit.get("visible") == "true" else "未开放"
        print(f"  [{i:>2}] {flag}  {unit.get('unitname', '')} {unit.get('name', '')}")
    unit_no = _pick("\n选择单元序号(0=全部):", len(units))

    hint = ("每个练习的正确率,如 100 或 70,100:" if mode == "accuracy"
            else "每个小节增加的秒数,如 30 或 20,60:")
    try:
        param = parse_numeric_param(input(hint))
    except ValueError as exc:
        print(f"参数错误:{exc}")
        return

    try:
        result = task.run(unit_no, param)
    except Stopped:
        print("已停止")
        return
    except WeLearnError as exc:
        print(f"运行失败:{exc}")
        return
    finally:
        task.close()

    print("\n运行结束")
    if mode == "accuracy":
        print(f"  方式1:{result['way1_succeed']} 成功 / {result['way1_failed']} 失败")
        print(f"  方式2:{result['way2_succeed']} 成功 / {result['way2_failed']} 失败")
    else:
        print(f"  共 {result['total']} 个小节,成功 {result['succeed']},失败 {result['failed']}")
        for i, err in enumerate(result["errors"], start=1):
            print(f"    第 {i} 个失败:{err}")


def main() -> int:
    print(BANNER)
    while True:
        print("  1. 刷完成度 / 正确率")
        print("  2. 刷学习时长")
        print("  0. 退出")
        choice = input("请选择:").strip()
        if choice == "1":
            run_flow("accuracy")
        elif choice == "2":
            run_flow("time")
        elif choice in ("0", "q", ""):
            return 0
        print()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(130)
