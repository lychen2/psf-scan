"""Generate placeholder splash + icon assets for the Windows installer.

Run from the repository root:

    python installer/_make_placeholder_resources.py

These are intentionally minimal stand-ins; replace with real artwork before a
public release.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "resources"
OUT.mkdir(parents=True, exist_ok=True)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def make_splash() -> None:
    img = Image.new("RGB", (480, 320), "#f5f5f5")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 479, 319], outline="#cccccc", width=1)
    d.text((240, 130), "PSF SCAN", fill="#1a4d8c", anchor="mm", font=_font(36, bold=True))
    d.text((240, 175), "Stage-scan PSF acquisition", fill="#4a4a4a", anchor="mm", font=_font(14))
    img.save(OUT / "splash.png")


def make_icons() -> None:
    icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    d.rounded_rectangle([16, 16, 240, 240], radius=24, fill="#1a4d8c")
    d.text((128, 128), "P", fill="#ffffff", anchor="mm", font=_font(140, bold=True))
    icon.save(OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(OUT / "installer-icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    # 256×256 PNG for Linux .desktop / .AppImage (XDG icon spec)
    icon.save(OUT / "icon.png", format="PNG")


def _rtf_escape(s: str) -> str:
    """Convert a Python str to RTF body bytes (ASCII-safe).

    Non-ASCII chars are emitted as ``\\uN?`` escape sequences so the file
    is plain ASCII on disk and renders correctly in any RTF reader.
    """
    out: list[str] = []
    for c in s:
        cp = ord(c)
        if cp < 128:
            if c in "\\{}":
                out.append("\\" + c)
            elif c == "\n":
                out.append("\\par\n")
            else:
                out.append(c)
        else:
            # \u takes a signed 16-bit integer; values >= 0x8000 wrap to negative.
            signed = cp if cp < 0x8000 else cp - 0x10000
            out.append(f"\\u{signed}?")
    return "".join(out)


def make_license() -> None:
    body = (
        "PSF Scan\n"
        "\n"
        "Copyright (c) 2026.\n"
        "\n"
        "This software is provided \"as is\". Use of this software\n"
        "constitutes acceptance of the applicable terms. No commercial\n"
        "redistribution without permission.\n"
    )
    rtf = (
        "{\\rtf1\\ansi\\deff0\n"
        "{\\fonttbl{\\f0\\fnil\\fcharset0 Calibri;}}\n"
        "\\viewkind4\\uc1\n"
        "\\pard\\sa120\\fs22\\f0\n"
        + _rtf_escape(body)
        + "}\n"
    )
    (OUT / "license.rtf").write_text(rtf, encoding="ascii")


if __name__ == "__main__":
    make_splash()
    make_icons()
    make_license()
    print("[resources] generated:", *(p.name for p in OUT.glob("*")))
