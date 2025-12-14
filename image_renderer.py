# coding: utf-8
"""
Utility helpers to build device view models and render them into PNG images.
This module relies on Pillow for basic drawing primitives so that we can
produce lightweight server-side images without adding heavy browser runtimes.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from io import BytesIO
from typing import Dict, Iterable, List, Optional

import pytz
from PIL import Image, ImageDraw, ImageFont

# basic colors
BG_COLOR = (15, 17, 21)
CARD_COLOR = (23, 26, 34)
TEXT_COLOR = (230, 238, 243)
MUTED_COLOR = (158, 167, 177)
LABEL_COLOR = (126, 136, 146)
BORDER_COLOR = (43, 48, 58)

STATUS_COLORS = {
    "在线": (46, 204, 113),
    "离线": (136, 146, 157),
    "待机": (241, 196, 15),
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/noto/NotoSansSC-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _parse_battery_from_text(text: str) -> Optional[int]:
    matchers = [
        r"电量[:：]?\s*(\d{1,3})%",
        r"🔋\s*(\d{1,3})%",
        r"\[(?:🔋)?(\d{1,3})%\s*.*?\]",
    ]
    for pat in matchers:
        m = re.search(pat, text)
        if m:
            try:
                pct = int(m.group(1))
                if 0 <= pct <= 100:
                    return pct
            except Exception:
                continue
    return None


def _normalize_device_type(raw: Optional[str]) -> str:
    if not raw:
        return "其他"
    txt = str(raw).lower()
    if any(k in txt for k in ["phone", "android", "ios", "mobile", "iphone", "手机"]):
        return "手机"
    if any(k in txt for k in ["computer", "pc", "desktop", "mac", "windows", "linux", "电脑"]):
        return "电脑"
    if any(k in txt for k in ["pad", "tablet", "平板", "ipad"]):
        return "平板"
    return "其他"


def _normalize_online_status(raw: Optional[str], device: dict) -> str:
    if raw is None:
        if device.get("using") or device.get("running"):
            return "在线"
        return "—"
    if isinstance(raw, bool):
        return "在线" if raw else "离线"
    txt = str(raw).lower()
    if txt in ("online", "on", "connected", "alive", "running"):
        return "在线"
    if txt in ("offline", "off", "disconnected", "dead"):
        return "离线"
    if txt in ("idle", "standby", "sleep", "waiting"):
        return "待机"
    return "—"


def _normalize_app_status(raw: Optional[str], device: dict) -> str:
    if raw:
        txt = str(raw).lower()
        if "run" in txt or txt in ("foreground", "active"):
            return "运行中"
        if "back" in txt or txt in ("background",):
            return "后台"
        if "stop" in txt or "idle" in txt:
            return "已锁屏"
    if device.get("running") or device.get("using"):
        return "运行中"
    if device.get("background"):
        return "后台"
    return "已锁屏"


def _normalize_platform(raw: Optional[str]) -> str:
    if not raw:
        return "—"
    return str(raw)


def _format_last_active(raw: Optional[object], tz: pytz.timezone) -> str:
    if raw in (None, "", "None"):
        return "—"
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "—"
    if isinstance(raw, datetime):
        try:
            return raw.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return raw.strftime("%Y-%m-%d %H:%M")
    return str(raw)


def build_device_view_models(devices: Dict[str, dict], timezone: str) -> List[dict]:
    tz = pytz.timezone(timezone) if timezone else pytz.UTC
    models: List[dict] = []
    for device_id, info in devices.items():
        name = info.get("show_name") or info.get("name") or device_id
        dtype_raw = info.get("type") or info.get("device_type")
        platform = info.get("platform") or info.get("os") or info.get("system")
        online_status = _normalize_online_status(info.get("online_status") or info.get("online"), info)
        app_status = _normalize_app_status(info.get("app_status"), info)
        app_name = info.get("app_name") or info.get("app") or "—"
        last_active = _format_last_active(
            info.get("last_active") or info.get("last_seen") or info.get("last_online"), tz
        )
        battery = info.get("battery_percent")
        if battery is None:
            battery = info.get("battery")
        if battery is None:
            battery = _parse_battery_from_text(app_name if app_name else "")
        try:
            if battery is not None:
                battery = max(0, min(100, int(battery)))
        except Exception:
            battery = None
        models.append(
            {
                "id": device_id,
                "name": name,
                "type": _normalize_device_type(dtype_raw),
                "platform": _normalize_platform(platform),
                "online_status": online_status,
                "current_app": app_name or "—",
                "app_status": app_status if app_status else "—",
                "last_active": last_active,
                "battery_percent": battery,
            }
        )
    return models


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font):
    """兼容 Pillow 版本的文本测量工具。"""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        pass
    try:
        return font.getsize(text)
    except Exception:
        return (0, 0)


def _draw_status_badge(draw: ImageDraw.ImageDraw, text: str, xy, font):
    color = STATUS_COLORS.get(text, (90, 96, 108))
    x1, y1 = xy
    text_w, text_h = _measure_text(draw, text, font)
def _draw_status_badge(draw: ImageDraw.ImageDraw, text: str, xy, font):
    color = STATUS_COLORS.get(text, (90, 96, 108))
    x1, y1 = xy
    text_w, text_h = draw.textsize(text, font=font)
    padding_x = 14
    padding_y = 8
    rect = [x1, y1, x1 + text_w + padding_x * 2, y1 + text_h + padding_y * 2]
    draw.rounded_rectangle(rect, radius=12, fill=color)
    draw.text((x1 + padding_x, y1 + padding_y), text, font=font, fill=BG_COLOR)
    return rect[2]


def _draw_info_block(draw: ImageDraw.ImageDraw, pos, label: str, value: str, label_font, value_font):
    x, y = pos
    draw.text((x, y), label, font=label_font, fill=LABEL_COLOR)
    draw.text((x, y + 18), value, font=value_font, fill=TEXT_COLOR)


def _draw_battery(draw: ImageDraw.ImageDraw, pos, percent: Optional[int]):
    x, y = pos
    if percent is None:
        draw.text((x, y), "电量", font=_load_font(13), fill=LABEL_COLOR)
        draw.text((x, y + 18), "—", font=_load_font(15), fill=TEXT_COLOR)
        return
    draw.text((x, y), "电量", font=_load_font(13), fill=LABEL_COLOR)
    draw.rounded_rectangle([x, y + 26, x + 200, y + 48], radius=8, outline=BORDER_COLOR, width=2, fill=(29, 33, 42))
    inner_width = int(196 * percent / 100)
    draw.rounded_rectangle([x + 2, y + 28, x + 2 + inner_width, y + 46], radius=6, fill=(52, 152, 219))
    draw.text((x + 210, y + 24), f"{percent}%", font=_load_font(15, bold=True), fill=TEXT_COLOR)


def render_device_usage_image(devices: Iterable[dict]) -> BytesIO:
    device_list = list(devices)
    if not device_list:
        device_list = [
            {
                "name": "暂无设备",
                "type": "其他",
                "platform": "—",
                "online_status": "—",
                "current_app": "—",
                "app_status": "—",
                "last_active": "—",
                "battery_percent": None,
            }
        ]

    width = 1200
    card_height = 210
    margin = 32
    spacing = 18
    canvas_height = margin + len(device_list) * (card_height + spacing) + margin
    img = Image.new("RGB", (width, canvas_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(22, bold=True)
    tag_font = _load_font(14, bold=True)
    label_font = _load_font(13)
    value_font = _load_font(15, bold=True)

    card_width = width - margin * 2
    for idx, device in enumerate(device_list):
        top = margin + idx * (card_height + spacing)
        left = margin
        # card background
        draw.rounded_rectangle(
            [left, top, left + card_width, top + card_height], radius=14, fill=CARD_COLOR, outline=BORDER_COLOR
        )

        # header row
        name = str(device.get("name", "—"))
        draw.text((left + 22, top + 18), name, font=title_font, fill=TEXT_COLOR)
        badge_x = left + card_width - 150
        badge_y = top + 12
        _draw_status_badge(draw, device.get("online_status", "—"), (badge_x, badge_y), tag_font)

        # info grid
        info_items = [
            ("设备类型", device.get("type", "—")),
            ("系统平台", device.get("platform", "—")),
            ("当前运行应用", device.get("current_app", "—")),
            ("应用状态", device.get("app_status", "—")),
            ("最近活跃时间", device.get("last_active", "—")),
        ]
        grid_left = left + 22
        grid_top = top + 64
        col_width = (card_width - 44 - 18) // 2
        for i, (label, value) in enumerate(info_items):
            col = i % 2
            row = i // 2
            x = grid_left + col * (col_width + 18)
            y = grid_top + row * 52
            _draw_info_block(draw, (x, y), label, str(value or "—"), label_font, value_font)

        # battery row spans width
        battery_y = top + card_height - 60
        _draw_battery(draw, (grid_left, battery_y), device.get("battery_percent"))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
