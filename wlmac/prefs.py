# 本文件本仓库新增(macOS 侧实现,协议参考上游)。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""macOS 本地偏好与钥匙串 —— 账号记在 JSON,密码只进系统钥匙串。

路径遵循 macOS 惯例:~/Library/Application Support/WeLearnHelper/config.json
密码用 Security.framework(kSecClassGenericPassword)保存,不落盘明文。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from . import KEYCHAIN_SERVICE

DEFAULT_DIR = Path.home() / "Library" / "Application Support" / "WeLearnHelper"


def _config_dir() -> Path:
    """WL_CONFIG_DIR 仅供测试隔离使用,正常运行走 macOS 惯例目录。"""
    custom = os.environ.get("WL_CONFIG_DIR")
    return Path(custom) if custom else DEFAULT_DIR

DEFAULTS: Dict[str, Any] = {
    "username": "",
    "remember_password": False,
    "mode": "accuracy",
    "param_accuracy": "100",
    "param_time": "30",
    "last_cid": None,
}

_SEC_IMPORT_ERROR = None
try:  # pyobjc 随 pywebview 一起安装;缺失时退化为 security 命令行
    from Foundation import NSMutableDictionary
    from Security import (SecItemAdd, SecItemCopyMatching, SecItemDelete,
                          kSecAttrAccount, kSecAttrService, kSecClass,
                          kSecClassGenericPassword, kSecMatchLimit,
                          kSecMatchLimitOne, kSecReturnData, kSecValueData)
except Exception as exc:  # pragma: no cover
    _SEC_IMPORT_ERROR = exc
    NSMutableDictionary = None


def load() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    path = _config_dir() / "config.json"
    try:
        if path.exists():
            stored = json.loads(path.read_text("utf-8"))
            if isinstance(stored, dict):
                data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except Exception:
        pass
    return data


def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    data = load()
    for key, value in (patch or {}).items():
        if key in DEFAULTS:
            data[key] = value
    try:
        folder = _config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "config.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        os.chmod(path, 0o600)
    except Exception:
        pass
    return data


def _base_query(account: str):
    query = NSMutableDictionary.alloc().init()
    query[kSecClass] = kSecClassGenericPassword
    query[kSecAttrService] = KEYCHAIN_SERVICE
    query[kSecAttrAccount] = account
    return query


def keychain_save(account: str, password: str) -> bool:
    if not account:
        return False
    if NSMutableDictionary is None:
        return _cli_save(account, password)
    try:
        SecItemDelete(_base_query(account))
        query = _base_query(account)
        query[kSecValueData] = password.encode("utf-8")
        status, _ = SecItemAdd(query, None)
        return status == 0
    except Exception:
        return False


def keychain_load(account: str) -> Optional[str]:
    if not account:
        return None
    if NSMutableDictionary is None:
        return _cli_load(account)
    try:
        query = _base_query(account)
        query[kSecReturnData] = True
        query[kSecMatchLimit] = kSecMatchLimitOne
        status, data = SecItemCopyMatching(query, None)
        if status == 0 and data is not None:
            return bytes(data).decode("utf-8")
    except Exception:
        pass
    return None


def keychain_delete(account: str) -> None:
    if not account:
        return
    if NSMutableDictionary is None:
        _cli_delete(account)
        return
    try:
        SecItemDelete(_base_query(account))
    except Exception:
        pass


# --- 无 pyobjc 时的兜底实现 ------------------------------------------------
def _cli_save(account: str, password: str) -> bool:
    try:
        subprocess.run(["security", "delete-generic-password", "-a", account,
                        "-s", KEYCHAIN_SERVICE], capture_output=True, check=False)
        result = subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE,
             "-w", password, "-U"], capture_output=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


def _cli_load(account: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE,
             "-w"], capture_output=True, check=False)
        if result.returncode == 0:
            return result.stdout.decode("utf-8").rstrip("\n")
    except Exception:
        pass
    return None


def _cli_delete(account: str) -> None:
    try:
        subprocess.run(["security", "delete-generic-password", "-a", account,
                        "-s", KEYCHAIN_SERVICE], capture_output=True, check=False)
    except Exception:
        pass
