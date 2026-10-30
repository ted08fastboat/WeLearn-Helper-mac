# 本文件本仓库新增。
# 协议逆向来源:YZBRH/Welearn_helper — 原作者 Avenshy,早期共同作者 SSmJaE,维护者 YZBRH / lxbsdsg。
# 许可证:GNU GPLv3,详见仓库根目录 LICENSE 与 NOTICE.md。
"""生成 macOS 应用图标(.icns):圆角矩形渐变 + 白色 W,与界面 Logo 一致。

    python tools/make_icon.py build/appicon.icns
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from AppKit import (NSBezierPath, NSBitmapImageRep, NSColor, NSFont,
                    NSFontAttributeName, NSFontWeightBold, NSForegroundColorAttributeName,
                    NSGradient, NSGraphicsContext, NSImage, NSMakeRect, NSString)
from Foundation import NSMakePoint

SIZE = 1024
INSET = 92
RADIUS = 208


def render_png(target: Path) -> None:
    image = NSImage.alloc().initWithSize_((SIZE, SIZE))
    image.lockFocus()
    NSGraphicsContext.currentContext().setImageInterpolation_(2)

    NSColor.clearColor().set()
    NSBezierPath.fillRect_(NSMakeRect(0, 0, SIZE, SIZE))

    rect = NSMakeRect(INSET, INSET, SIZE - 2 * INSET, SIZE - 2 * INSET)
    squircle = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, RADIUS, RADIUS)
    squircle.addClip()

    top = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.30, 0.60, 1.00, 1.0)
    bottom = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.18, 0.82, 0.66, 1.0)
    gradient = NSGradient.alloc().initWithStartingColor_endingColor_(top, bottom)
    gradient.drawInRect_angle_(rect, -50)

    # 顶部柔和高光(用渐变而不是圆形,避免出现硬边)
    gloss = NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.15),
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.0))
    gloss.drawInRect_angle_(rect, -90)

    font = NSFont.systemFontOfSize_weight_(470, NSFontWeightBold)
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: NSColor.whiteColor()}
    text = NSString.stringWithString_("W")
    bounds = text.sizeWithAttributes_(attrs)
    text.drawAtPoint_withAttributes_(
        NSMakePoint((SIZE - bounds.width) / 2.0, (SIZE - bounds.height) / 2.0 + 26), attrs)

    image.unlockFocus()

    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    data = rep.representationUsingType_properties_(4, {})   # 4 = PNG
    target.write_bytes(bytes(data))


def build_icns(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        master = tmp_path / "icon_1024.png"
        render_png(master)

        iconset = tmp_path / "AppIcon.iconset"
        iconset.mkdir()
        plan = [(16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
                (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
                (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x")]
        for pixels, name in plan:
            subprocess.run(["sips", "-z", str(pixels), str(pixels), str(master),
                            "--out", str(iconset / f"icon_{name}.png")],
                           check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output)], check=True)
    print(f"icon → {output}")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "build/appicon.icns")
    build_icns(target)
