"""Check OracleAI dark-theme text and non-text semantic color pairs."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = (ROOT / "miniapp" / "css" / "00-tokens.css").read_text(encoding="utf-8")


def token_value(name: str) -> str:
    match = re.search(rf"{re.escape(name)}:\s*([^;]+);", TOKENS)
    if not match:
        raise ValueError(f"missing {name}")
    return match.group(1).strip()


def parse_color(value: str) -> tuple[int, int, int, float]:
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if hex_match:
        raw = hex_match.group(1)
        return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    rgba_match = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)", value)
    if rgba_match:
        return (
            int(float(rgba_match.group(1))),
            int(float(rgba_match.group(2))),
            int(float(rgba_match.group(3))),
            float(rgba_match.group(4) or 1),
        )
    raise ValueError(f"unsupported color value: {value}")


def resolve(name: str) -> tuple[int, int, int, float]:
    return parse_color(token_value(name))


def blend(foreground: tuple[int, int, int, float], background: tuple[int, int, int, float]) -> tuple[int, int, int, float]:
    alpha = foreground[3] + background[3] * (1 - foreground[3])
    if alpha == 0:
        return (0, 0, 0, 0)
    rgb = tuple(round((foreground[i] * foreground[3] + background[i] * background[3] * (1 - foreground[3])) / alpha) for i in range(3))
    return rgb + (alpha,)


def luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= .04045 else ((srgb + .055) / 1.055) ** 2.4)
    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]


def ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    light = max(luminance(foreground), luminance(background))
    dark = min(luminance(foreground), luminance(background))
    return (light + .05) / (dark + .05)


def report(label: str, foreground: tuple[int, int, int, float], background: tuple[int, int, int, float], threshold: float) -> None:
    composite = blend(foreground, background)
    value = ratio(composite[:3], background[:3])
    status = "PASS" if value >= threshold else "REVIEW"
    print(f"{status}: {label} = {value:.2f}:1 (target {threshold:.1f}:1; composited rgb={composite[:3]})")


primary_bg = resolve("--color-bg-primary")
secondary_bg = resolve("--color-bg-secondary")
elevated_bg = resolve("--color-bg-elevated")

print("TEXT / normal text threshold 4.5:1")
for foreground, background, label in [
    ("--color-text-primary", "--color-bg-primary", "primary text on primary background"),
    ("--color-text-secondary", "--color-bg-primary", "secondary text on primary background"),
    ("--color-text-muted", "--color-bg-primary", "muted text on primary background"),
    ("--color-text-primary", "--color-bg-secondary", "primary text on secondary background"),
    ("--color-text-primary", "--color-bg-elevated", "primary text on elevated background"),
    ("--color-on-accent", "--color-accent-strong", "button text on strong accent"),
    ("--color-on-accent", "--color-accent-deep", "button text on deep accent"),
]:
    report(label, resolve(foreground), resolve(background), 4.5)

print("NON-TEXT / UI indicators threshold 3:1")
for foreground in [
    "--color-accent-strong",
    "--color-accent-deep",
    "--color-accent-secondary",
    "--color-success",
    "--color-warning",
    "--color-error",
    "--color-info",
    "--color-border-strong",
]:
    report(f"{foreground} against --color-bg-primary", resolve(foreground), primary_bg, 3.0)

print("NON-TEXT / solid focus outline threshold 3:1")
report("solid focus outline --color-accent-strong against --color-bg-primary", resolve("--color-accent-strong"), primary_bg, 3.0)
