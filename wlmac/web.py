# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""本地 HTTP API —— 界面(WKWebView)通过 127.0.0.1 上的这套接口驱动后台任务。

只监听回环地址;不对外网暴露。所有响应统一 {ok, ...} 结构,错误信息直接可展示。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory

from . import (APP_NAME, ORIGINAL_AUTHOR, UPSTREAM_REPO, __version__, prefs)
from .service import service as default_service

RESOURCES = Path(__file__).parent / "resources"


def create_app(svc=None) -> Flask:
    svc = svc or default_service
    app = Flask(__name__, static_folder=None)
    app.config["JSON_AS_ASCII"] = False

    # ------------------------------------------------------------------ 静态页
    @app.get("/")
    def index():
        return send_from_directory(RESOURCES, "index.html")

    @app.get("/assets/<path:name>")
    def assets(name: str):
        return send_from_directory(RESOURCES, name)

    # ------------------------------------------------------------------ 启动信息
    @app.get("/api/boot")
    def boot():
        stored = prefs.load()
        password = ""
        if stored.get("remember_password") and stored.get("username"):
            password = prefs.keychain_load(stored["username"]) or ""
        return jsonify(ok=True, version=__version__, app=APP_NAME,
                       upstream=UPSTREAM_REPO, author=ORIGINAL_AUTHOR,
                       prefs=stored, password=password)

    @app.post("/api/prefs")
    def save_prefs():
        payload = request.get_json(silent=True) or {}
        patch = {k: v for k, v in payload.items()
                 if k in ("username", "remember_password", "mode",
                          "param_accuracy", "param_time", "last_cid")}
        saved = prefs.save(patch)
        return jsonify(ok=True, prefs=saved)

    # ------------------------------------------------------------------ 会话
    @app.post("/api/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        mode = payload.get("mode") or svc.mode
        result = svc.login(username, password, mode)
        if result.get("ok"):
            remember = bool(payload.get("remember"))
            prefs.save({"username": username, "remember_password": remember, "mode": mode})
            if remember:
                prefs.keychain_save(username, password)
            else:
                prefs.keychain_delete(username)
        return jsonify(result)

    @app.post("/api/logout")
    def logout():
        if svc.busy():
            return jsonify(ok=False, error="任务正在进行,请先停止"), 409
        svc.logout()
        return jsonify(ok=True)

    @app.post("/api/mode")
    def mode():
        payload = request.get_json(silent=True) or {}
        return jsonify(svc.set_mode(payload.get("mode")))

    @app.post("/api/refresh")
    def refresh():
        return jsonify(svc.refresh_courses())

    @app.post("/api/course")
    def course():
        payload = request.get_json(silent=True) or {}
        return jsonify(svc.select_course(payload.get("cid")))

    @app.post("/api/sections")
    def sections():
        payload = request.get_json(silent=True) or {}
        try:
            unit_no = int(payload.get("unit"))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="单元编号必须是数字"), 400
        return jsonify(svc.load_sections(unit_no))

    # ------------------------------------------------------------------ 任务
    @app.post("/api/start")
    def start():
        payload = request.get_json(silent=True) or {}
        return jsonify(svc.start(payload.get("units", 0), payload.get("sections"),
                                 str(payload.get("param", ""))))

    @app.post("/api/stop")
    def stop():
        return jsonify(svc.stop())

    # ------------------------------------------------------------------ 状态轮询
    @app.get("/api/state")
    def state():
        try:
            after = int(request.args.get("after", "0"))
        except ValueError:
            after = 0
        return jsonify(ok=True, **svc.snapshot(after))

    # ------------------------------------------------------------------ 工具
    @app.post("/api/export-log")
    def export_log():
        snapshot: Dict[str, Any] = svc.snapshot(0)
        target = Path.home() / "Downloads" / f"WeLearn-Helper-{time.strftime('%Y%m%d-%H%M%S')}.log"
        lines = [f"{stamp}  {text}" for _, stamp, text in snapshot["logs"]]
        body = "\n".join(lines) if lines else "(无日志)"
        try:
            target.write_text(body, "utf-8")
        except Exception as exc:
            return jsonify(ok=False, error=f"写入失败:{exc}")
        return jsonify(ok=True, path=str(target))

    return app
