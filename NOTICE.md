# 来源与署名(NOTICE)

本仓库是 **macOS 重写版**,不是原创协议实现。所有协议细节(登录密文、OIDC 流程、SCO 接口)均来自上游项目的逆向成果。

## 上游项目

| 项 | 内容 |
| --- | --- |
| 原项目 | **WELearnToSleep**(WELearn 学习辅助工具) |
| 原作者 | **Avenshy** — https://github.com/Avenshy |
| 早期共同作者 | **SSmJaE** |
| 现维护项目 | **YZBRH/Welearn_helper** — https://github.com/YZBRH/Welearn_helper |
| 现维护者 | **YZBRH** — https://github.com/YZBRH 、**lxbsdsg** — https://github.com/lxbsdsg |
| 上游许可证 | GNU General Public License v3.0 |

上游 README 原文:

> 本项目原作者为 https://github.com/Avenshy
> 原项目已停止更新维护,无法直接使用,现进行修正调整后已恢复其原功能
> 该脚本版权归于原作者,本项目仅进行修复与优化

## 本仓库做了什么

按 GPLv3 第 5 条,此处说明修改内容:

- **保留**:协议层(`wlmac/net.py`、`accuracy.py`、`duration.py`)是上游 `welearn_common.py`、`welearn_accuracy.py`、`welearn_time.py` 的移植与加固,请求序列、提交字段、伪造的 cmi 报文与上游逐字一致。
- **新增**:macOS 原生窗口外壳(pywebview/WKWebView)、Flask 本地 API、服务层的单任务槽位与状态快照、钥匙串与偏好存储、深/浅色界面、`.app` 打包脚本、终端模式、回归测试。
- **修正**:登录密文的时间戳取整与浏览器 JS 对齐(上游浮点除法导致 `T1 % 100` 不满足校验不变量)、刷时长心跳在任务结束后不退出、全部单元模式可能死循环、多协程并发共用同一 TLS 会话、登录 Location 按下标硬取等问题。详见 README「和上游比,改了什么」。

## 许可证

本项目整体遵循 **GNU General Public License v3.0**,与上游一致,见 [LICENSE](LICENSE)。
你可以自由使用、修改、再分发,但 derivatives 必须同样以 GPLv3 开源,并保留上述署名。

**本项目免费、开源,禁止售卖。**

## 免责

本项目为协议研究与个人学习辅助工具,与上海外语教育出版社及 WeLearn 平台无关,不代表其立场。
使用本工具产生的任何后果由使用者自行承担;请优先遵守所在课程与学校的规定。
