#!/bin/bash
# 构建 WeLearn Helper.app(需要 macOS + Xcode 命令行工具)
set -euo pipefail
cd "$(dirname "$0")"

# 1. 找 Python:优先用项目内 .venv,其次用上级目录的 .venv,再退回系统 python3
if [ -x .venv/bin/python ]; then
  PY=./.venv/bin/python
elif [ -x ../.venv/bin/python ]; then
  PY=../.venv/bin/python
else
  PY=python3
fi
echo "使用解释器:$PY"

"$PY" -c "import flask, tls_client, webview" 2>/dev/null || {
  echo "缺少依赖,正在安装…"
  "$PY" -m pip install -q -r requirements.txt
}

# 2. 生成图标
"$PY" tools/make_icon.py build/appicon.icns

# 3. 打包
"$PY" -m PyInstaller --noconfirm --clean WeLearnHelper.spec

# 4. ad-hoc 签名 + 清理隔离属性(本机构建后可直接双击)
APP="dist/WeLearn Helper.app"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "⚠️  签名失败,可能仍需手动允许打开"
xattr -cr "$APP" 2>/dev/null || true
rm -rf "dist/WeLearn Helper"   # 删掉 PyInstaller 的中间目录,只留 .app

echo
echo "✅ 构建完成:$APP"
du -sh "$APP" | awk '{print "   体积:" $1}'
echo "   双击打开即可;首次打开若被 Gatekeeper 拦,右键 → 打开。"
