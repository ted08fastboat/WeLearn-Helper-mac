# 本文件移植自 YZBRH/Welearn_helper 的逆向实现。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""WeLearn(学乐)平台协议层 —— 由上游 Welearn_helper 逆向结果移植并加固。

要点(逆向结论,勿随意改动):
1. welearn.sflep.com 前置 WAF 按 TLS 指纹 + UA 拦截,普通 requests/curl 会被 405,
   必须用 tls_client 的 chrome_120 指纹才能拿到 302 与正常页面。
2. 登录密码不是明文:前端 common.js 里 generateCipherText() 把
   "毫秒时间戳补齐后的 T1" + "*" + "密码 UTF-8 的十六进制" 做 base64 后提交,
   同时附带 ts=T1。T1 = T0//100*100 + ((T0>>16 & 0xFF) ^ 各字节) % 100。
3. 登录是标准 OIDC authorization code + PKCE(S256) 流程:
   prelogin.aspx 302 → 取 code_challenge/state → POST sso.sflep.com/idsvr/account/login
   → 跟随返回的 data 路径重定向链,完成后 Cookie 生效。
4. 刷课数据走 /Ajax/SCO.aspx 的 action 系列:startsco160928 / setscoinfo /
   savescoinfo160928 / getscoinfo_v7 / keepsco_with_getticket_with_updatecmitime。
"""
from __future__ import annotations

import base64
import re
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import tls_client

from .errors import LoginError, Stopped, WeLearnError

AJAX_BASE = "https://welearn.sflep.com"
SCO_AJAX_URL = f"{AJAX_BASE}/Ajax/SCO.aspx"

PRELOGIN_URL = ("https://welearn.sflep.com/user/prelogin.aspx"
                "?loginret=http://welearn.sflep.com/user/loginredirect.aspx")
SSO_LOGIN_URL = "https://sso.sflep.com/idsvr/account/login"
COURSE_LIST_URL = f"{AJAX_BASE}/ajax/authCourse.aspx?action=gmc"
UNITS_URL = f"{AJAX_BASE}/ajax/StudyStat.aspx"

# 浏览器指纹:与上游一致,换掉大概率被 WAF 挡回 405
CLIENT_IDENTIFIER = "chrome_120"
REQUEST_TIMEOUT = 30
LOGIN_MAX_ATTEMPTS = 6

Numeric = Union[int, Tuple[int, int]]


def _noop(msg: str) -> None:
    pass


class _SimpleSession:
    """给 tls_client.Session 加一层薄封装:统一超时、统一异常类型。"""

    def __init__(self, session: Any, on_log: Callable[[str], None] = _noop):
        self.session = session
        self.on_log = on_log

    def _call(self, method: str, url: str, **kwargs) -> Any:
        kwargs.setdefault("timeout_seconds", REQUEST_TIMEOUT)
        try:
            return getattr(self.session, method)(url, **kwargs)
        except Exception as exc:  # tls_client 抛的是各类原生错误
            raise WeLearnError(f"网络请求失败:{exc}") from exc


def new_session(on_log: Callable[[str], None] = _noop) -> _SimpleSession:
    raw = tls_client.Session(client_identifier=CLIENT_IDENTIFIER, debug=False)
    raw.timeout_seconds = REQUEST_TIMEOUT
    return _SimpleSession(raw, on_log)


def close_session(session: Any) -> None:
    inner = getattr(session, "session", session)
    try:
        inner.close()
    except Exception:
        pass


def to_hex_byte_array(byte_array: bytes) -> str:
    return "".join([f"{byte:02x}" for byte in byte_array])


def generate_cipher_text(password: str, now_ms: Optional[int] = None) -> Tuple[str, int]:
    """复刻 common.js 的 generateCipherText(),返回 (base64 密文, 用于 ts 的时间戳)。

    注意:上游 Python 版写成 `int((T0 / 100) * 100 + remainder)`,浮点除法会保留
    T0 的百位以下部分,导致 T1 % 100 != 校验值;真实浏览器是 `Math.floor(T0/100)*100`,
    这里按浏览器行为对齐,保证 T1 落在当前 100ms 区间且满足 T1 % 100 == 校验值。
    """
    t0 = int(round(now_ms if now_ms is not None else time.time() * 1000))
    payload = password.encode("utf-8")
    v = (t0 >> 16) & 0xFF
    for byte in payload:
        v ^= byte
    remainder = v % 100
    t1 = (t0 // 100) * 100 + remainder
    cipher = f"{t1}*" + to_hex_byte_array(payload)
    return base64.b64encode(cipher.encode("utf-8")).decode("utf-8"), t1


def parse_numeric_param(text: str) -> Numeric:
    """'30' -> 30 ; '10,30' -> (10, 30)。非法输入抛 ValueError(消息直接给用户看)。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("请输入数值")
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 2:
            raise ValueError(f"格式异常:{text!r}(区间格式为 最小值,最大值)")
        try:
            lo, hi = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError(f"格式异常:{text!r}(区间内必须是整数)")
        if lo > hi:
            raise ValueError(f"格式异常:{text!r}(下限大于上限)")
        if lo < 0:
            raise ValueError(f"格式异常:{text!r}(不能为负数)")
        return lo, hi
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"格式异常:{text!r}(只接受整数,或用英文逗号分隔的区间)")
    if value < 0:
        raise ValueError(f"格式异常:{text!r}(不能为负数)")
    return value


def _query_dict(url: str) -> Dict[str, str]:
    """从 URL 里取查询参数(替代上游按 & 下标硬取,顺序变了就崩)。"""
    parsed = urllib.parse.urlparse(url)
    return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items() if v}


def login(session: _SimpleSession, user: str, pwd: str,
          on_log: Callable[[str], None] = _noop,
          stop_event: Optional[threading.Event] = None,
          max_attempts: int = LOGIN_MAX_ATTEMPTS) -> None:
    """完成 OIDC 登录。密码错误抛 LoginError,被停止抛 Stopped。"""
    def check_stop() -> None:
        if stop_event is not None and stop_event.is_set():
            raise Stopped()

    check_stop()
    on_log("正在连接学乐平台 SSO…")
    response = session._call("get", PRELOGIN_URL)
    location = response.headers.get("Location") or ""
    if not location:
        raise LoginError(f"登录入口异常(HTTP {response.status_code}),站点可能维护中")

    params = _query_dict(location)
    code_challenge, state = params.get("code_challenge"), params.get("state")
    if not code_challenge or not state:
        raise LoginError("登录入口返回的参数不完整(code_challenge/state 缺失)")

    rturl = (
        "/connect/authorize/callback?client_id=welearn_web"
        "&redirect_uri=https%3A%2F%2Fwelearn.sflep.com%2Fsignin-sflep"
        "&response_type=code&scope=openid%20profile%20email%20phone%20address"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
        f"&state={state}&x-client-SKU=ID_NET472&x-client-ver=6.32.1.0"
    )

    for attempt in range(1, max_attempts + 1):
        check_stop()
        cipher, ts = generate_cipher_text(pwd)
        response = session._call("post", SSO_LOGIN_URL, data={
            "rturl": rturl,
            "account": user,
            "pwd": cipher,
            "ts": str(ts),
        })

        try:
            payload = response.json()
        except Exception:
            raise LoginError(f"登录接口返回非 JSON(HTTP {response.status_code}),"
                             "通常是被风控拦截,请稍后重试")

        code = payload.get("code", -1)
        if code == 1:
            raise LoginError("账号或密码错误")

        if code == -1:
            on_log(f"服务端要求重试({attempt}/{max_attempts})…")
            time.sleep(0.6)
            continue

        next_url = "https://sso.sflep.com/idsvr" + str(payload.get("data") or "")
        # 手动跟随重定向:每跳都要带上会话 Cookie,交给库自动跳会丢状态
        for _ in range(12):
            check_stop()
            resp = session._call("get", next_url)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    break
                next_url = location
            else:
                break

        if code == 0:
            on_log("登录成功")
            return

    raise LoginError("登录重试次数过多,请稍后再试(常见于密码错误或站点繁忙)")


def fetch_courses(session: _SimpleSession) -> List[dict]:
    response = session._call("get", COURSE_LIST_URL,
                             headers={"Referer": f"{AJAX_BASE}/2019/student/index.aspx"})
    if response.status_code != 200:
        raise WeLearnError(f"课程列表请求失败(HTTP {response.status_code})")
    try:
        data = response.json()
    except Exception:
        raise WeLearnError("课程列表返回异常,可能是登录态失效,请重新登录")
    courses = data.get("clist") or []
    if not courses:
        raise WeLearnError("没有查询到课程:请确认账号已加入班级,或稍后重试")
    return courses


def get_course_ids(session: _SimpleSession, cid: str) -> Tuple[str, str]:
    """从课程信息页里抠出 uid / classid —— 后续所有统计接口都依赖这两个值。"""
    response = session._call("get", f"{AJAX_BASE}/student/course_info.aspx?cid={cid}")
    text = response.text or ""
    uid_match = re.search(r'"uid":(.*?),', text)
    class_match = re.search(r'"classid":"(.*?)"', text)
    if not uid_match or not class_match:
        raise WeLearnError("课程信息解析失败(未找到 uid/classid),课程可能已结束")
    return uid_match.group(1).strip(), class_match.group(1)


def fetch_units(session: _SimpleSession, cid: str, uid: str) -> List[dict]:
    response = session._call("get", UNITS_URL,
                             params={"action": "courseunits", "cid": cid, "uid": uid},
                             headers={"Referer": f"{AJAX_BASE}/2019/student/course_info.aspx"})
    try:
        units = response.json()["info"]
    except Exception:
        raise WeLearnError("单元列表返回异常,课程可能尚未生成学习单元")
    if not units:
        raise WeLearnError("该课程没有可用的学习单元")
    return units


def fetch_sections(session: _SimpleSession, cid: str, uid: str,
                   unit_index: int, classid: str) -> List[dict]:
    """unit_index 为 0-based 接口参数;只读,不提交任何学习数据。"""
    response = session._call(
        "get",
        f"{UNITS_URL}?action=scoLeaves&cid={cid}&uid={uid}"
        f"&unitidx={unit_index}&classid={classid}",
        headers={"Referer": f"{AJAX_BASE}/2019/student/course_info.aspx?cid={cid}"},
    )
    text = response.text or ""
    if "异常" in text or "出错了" in text:
        raise WeLearnError("单元不存在或已到末尾")
    try:
        return response.json()["info"]
    except Exception:
        raise WeLearnError("小节列表返回异常,请重试")


def normalize_targets(units: Any, sections: Any = None
                      ) -> Tuple[bool, Optional[List[int]], Optional[Dict[int, List[int]]]]:
    """把界面传入的目标解析成 (是否全部单元, 单元编号列表, {单元编号: [小节编号]})。

    units:    0/None=全部单元;正整数=单个单元;非空列表=多个单元
    sections: None/{}=整单元;正整数=该单元单个小节;{单元编号: [小节编号]}=按单元多选
    非法输入抛 ValueError(消息直接展示给用户)。
    """
    if isinstance(units, str):
        raise ValueError("单元编号格式错误(不支持字符串)")
    all_units = units in (0, None)
    if all_units:
        unit_list: Optional[List[int]] = None
    elif isinstance(units, int):
        if units < 1:
            raise ValueError("单元编号从 1 开始")
        unit_list = [units]
    else:
        try:
            unit_list = sorted({int(u) for u in units})
        except (TypeError, ValueError):
            raise ValueError("单元编号格式错误")
        if not unit_list:
            raise ValueError("未选择任何单元(勾选单元,或选择全部单元)")
        if unit_list[0] < 1:
            raise ValueError("单元编号从 1 开始")

    if isinstance(sections, str):
        raise ValueError("小节编号格式错误(不支持字符串)")
    if sections in (None, {}, 0):
        return all_units, unit_list, None
    if all_units:
        raise ValueError("指定小节时必须选择具体单元(不能与「全部单元」同用)")

    if isinstance(sections, dict):
        section_map: Dict[int, List[int]] = {}
        for unit_no, secs in sections.items():
            if isinstance(secs, str):
                raise ValueError("小节编号格式错误(不支持字符串)")
            try:
                uno, sec_list = int(unit_no), [int(s) for s in secs]
            except (TypeError, ValueError):
                raise ValueError("小节编号格式错误")
            sec_list = sorted(set(sec_list))
            if sec_list and sec_list[0] < 1:
                raise ValueError("小节编号从 1 开始")
            if sec_list:
                section_map[uno] = sec_list
    else:
        try:
            sec = int(sections)
        except (TypeError, ValueError):
            raise ValueError("小节编号格式错误")
        if sec < 1:
            raise ValueError("小节编号从 1 开始")
        section_map = {u: [sec] for u in unit_list or []}

    if not section_map:
        return all_units, unit_list, None
    for uno in section_map:
        if uno not in (unit_list or []):
            raise ValueError(f"单元 {uno} 不在已选单元内,无法为其指定小节")
    return all_units, unit_list, section_map
