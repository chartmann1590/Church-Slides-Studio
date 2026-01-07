from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.utils.files import sanitize_filename


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    if font_path:
        path = Path(font_path)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    for fallback in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        path = Path(fallback)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _default_background(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, "#0f1a2b")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(14 + (30 - 14) * ratio)
        g = int(26 + (45 - 26) * ratio)
        b = int(43 + (70 - 43) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return image


def _load_background(path: Path | None, size: tuple[int, int]) -> Image.Image:
    if path and path.exists():
        image = Image.open(path).convert("RGB")
        target_w, target_h = size
        src_w, src_h = image.size
        scale = max(target_w / src_w, target_h / src_h)
        resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.LANCZOS)
        left = (resized.width - target_w) // 2
        top = (resized.height - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))
    return _default_background(size)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        if draw.textlength(word, font=font) > max_width:
            if current:
                lines.append(current)
                current = ""
            for chunk in _split_long_word(word, font, max_width, draw):
                lines.append(chunk)
            continue
        trial = f"{current} {word}".strip()
        if not current or draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _split_long_word(word: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    chunks: list[str] = []
    remaining = word
    while remaining:
        if draw.textlength(remaining, font=font) <= max_width:
            chunks.append(remaining)
            break
        low, high = 1, len(remaining)
        best = 1
        while low <= high:
            mid = (low + high) // 2
            candidate = remaining[:mid] + "-"
            if draw.textlength(candidate, font=font) <= max_width:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if best <= 1:
            chunks.append(remaining[:1])
            remaining = remaining[1:]
        else:
            chunks.append(remaining[:best] + "-")
            remaining = remaining[best:]
    return chunks


def _fit_title_font(
    title: str,
    font_path: str,
    start_size: int,
    min_size: int,
    max_width: int,
    max_height: int,
    line_spacing: float,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    scratch = Image.new("RGB", (10, 10), "#000")
    draw = ImageDraw.Draw(scratch)
    for size in range(start_size, max(min_size, 10) - 1, -2):
        font = _load_font(font_path, size)
        lines = _wrap_text(title, font, max_width, draw)
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + int((ascent + descent) * line_spacing)
        total_height = line_height * max(1, len(lines))
        if total_height <= max_height:
            return font, lines
    font = _load_font(font_path, min_size)
    lines = _wrap_text(title, font, max_width, draw)
    return font, lines


def _prepare_lines(
    body_lines: list[str],
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for raw in body_lines:
        if raw.strip() == "":
            prepared.append({"text": "", "blank": True})
            continue
        for wrapped in _wrap_text(raw, font, max_width, draw):
            prepared.append({"text": wrapped, "blank": False})
    return prepared


def _paginate_lines(
    lines: list[dict[str, Any]],
    line_height: int,
    blank_height: int,
    max_height: int,
) -> list[list[dict[str, Any]]]:
    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    height = 0
    for line in lines:
        needed = blank_height if line["blank"] else line_height
        if current and height + needed > max_height:
            pages.append(current)
            current = []
            height = 0
        current.append(line)
        height += needed
    if current:
        pages.append(current)
    return pages or [[]]


def _draw_wrapped_text(
    image: Image.Image,
    lines: list[dict[str, Any]],
    box: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    color: str,
    stroke_color: str,
    stroke_width: int,
    line_spacing: float,
    align: str,
    center_vertical: bool,
) -> None:
    draw = ImageDraw.Draw(image)
    x, y, width, height = box
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + int((ascent + descent) * line_spacing)
    blank_height = max(10, int(line_height * 0.45))
    total_height = sum(blank_height if line["blank"] else line_height for line in lines)
    if center_vertical and total_height < height:
        start_y = y + (height - total_height) // 2
    else:
        start_y = y
    cursor_y = start_y
    for line in lines:
        if line["blank"]:
            cursor_y += blank_height
            continue
        text = line["text"]
        text_width = draw.textlength(text, font=font)
        if align == "center":
            text_x = x + (width - text_width) // 2
        else:
            text_x = x
        draw.text(
            (text_x, cursor_y),
            text,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color,
        )
        cursor_y += line_height


def _draw_lines_at_y(
    image: Image.Image,
    lines: list[str],
    x: int,
    width: int,
    start_y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    stroke_color: str,
    stroke_width: int,
    line_spacing: float,
    align: str,
) -> int:
    draw = ImageDraw.Draw(image)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + int((ascent + descent) * line_spacing)
    cursor_y = start_y
    for line in lines:
        text_width = draw.textlength(line, font=font)
        text_x = x + (width - text_width) // 2 if align == "center" else x
        draw.text(
            (text_x, cursor_y),
            line,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color,
        )
        cursor_y += line_height
    return cursor_y


def _page_has_text(page: list[dict[str, Any]]) -> bool:
    return any((not line["blank"]) and line["text"].strip() for line in page)


def render_slide_images(
    slide_specs: list[dict[str, Any]],
    output_dir: Path,
    settings: dict[str, Any],
    title_bg_path: Path | None = None,
    content_bg_path: Path | None = None,
) -> list[dict[str, Any]]:
    slide_width = max(1, int(settings.get("slide_width", 1920)))
    slide_height = max(1, int(settings.get("slide_height", 1080)))
    size = (slide_width, slide_height)

    title_font_size = int(settings.get("title_font_size", 96))
    title_font_min = int(settings.get("title_font_min", 60))
    body_font = _load_font(settings.get("body_font_path", ""), int(settings.get("body_font_size", 72)))
    label_font = _load_font(settings.get("label_font_path", ""), int(settings.get("label_font_size", 48)))
    subtitle_font = _load_font(settings.get("label_font_path", ""), max(28, int(settings.get("label_font_size", 48)) - 14))

    text_color = settings.get("text_color", "#F8F7F2")
    stroke_color = settings.get("stroke_color", "#1A1A1A")
    stroke_width = int(settings.get("stroke_width", 6))
    line_spacing = float(settings.get("line_spacing", 0.22))
    centered_sections = {s.lower() for s in settings.get("centered_sections", [])}

    title_box = settings.get("title_box", [120, 230, 1080, 700])
    label_pos = settings.get("label_pos", [120, 120])
    content_box = settings.get("content_box", [140, 220, 1640, 760])

    slides: list[dict[str, Any]] = []
    global_index = 1
    current_label = ""
    current_slide_index = 1

    for spec in slide_specs:
        label = spec.get("label", "Section")
        title = spec.get("title", "")
        subtitle = spec.get("subtitle", "")
        kind = spec.get("kind", "content")

        if kind == "title":
            current_label = label
            current_slide_index = 1
            image = _load_background(title_bg_path, size)
            draw = ImageDraw.Draw(image)
            draw.text(
                (label_pos[0], label_pos[1]),
                label,
                font=label_font,
                fill=text_color,
                stroke_width=stroke_width,
                stroke_fill=stroke_color,
            )
            fitted_font, wrapped = _fit_title_font(
                title,
                settings.get("title_font_path", ""),
                title_font_size,
                title_font_min,
                title_box[2],
                title_box[3],
                line_spacing,
            )
            ascent, descent = fitted_font.getmetrics()
            line_height = ascent + descent + int((ascent + descent) * line_spacing)
            title_block_height = line_height * max(1, len(wrapped))
            subtitle_lines = _wrap_text(subtitle, subtitle_font, title_box[2], ImageDraw.Draw(Image.new("RGB", (10, 10))))
            sub_ascent, sub_descent = subtitle_font.getmetrics()
            sub_line_height = sub_ascent + sub_descent + int((sub_ascent + sub_descent) * line_spacing)
            subtitle_block_height = sub_line_height * len(subtitle_lines) if subtitle else 0
            gap = 18 if subtitle else 0
            total_height = title_block_height + gap + subtitle_block_height
            start_y = title_box[1] + (title_box[3] - total_height) // 2
            cursor_y = _draw_lines_at_y(
                image,
                wrapped,
                title_box[0],
                title_box[2],
                start_y,
                fitted_font,
                text_color,
                stroke_color,
                stroke_width,
                line_spacing,
                align="center",
            )
            if subtitle:
                _draw_lines_at_y(
                    image,
                    subtitle_lines,
                    title_box[0],
                    title_box[2],
                    cursor_y + gap,
                    subtitle_font,
                    text_color,
                    stroke_color,
                    max(2, stroke_width - 2),
                    line_spacing,
                    align="center",
                )
            safe_label = sanitize_filename(label)
            filename = f"{global_index:02d} {safe_label} {current_slide_index}.jpg"
            path = output_dir / filename
            image.save(path, format="JPEG", quality=92)
            slides.append({"filename": filename, "path": str(path)})
            global_index += 1
            current_slide_index += 1
            continue

        if current_label != label:
            current_label = label
            current_slide_index = 1

        body_lines = [line for line in spec.get("body", [])]
        heading_text = title if label.lower() in centered_sections and title else label
        prep_draw = ImageDraw.Draw(Image.new("RGB", (10, 10), "#000"))
        prepared = _prepare_lines(body_lines, body_font, content_box[2], prep_draw)
        ascent, descent = body_font.getmetrics()
        line_height = ascent + descent + int((ascent + descent) * line_spacing)
        blank_height = max(10, int(line_height * 0.45))
        pages = _paginate_lines(prepared, line_height, blank_height, content_box[3])

        for page in pages:
            if not _page_has_text(page):
                continue
            frame = _load_background(content_bg_path, size)
            _draw_wrapped_text(
                frame,
                page,
                (content_box[0], content_box[1], content_box[2], content_box[3]),
                body_font,
                text_color,
                stroke_color,
                stroke_width,
                line_spacing,
                align="center" if label.lower() in centered_sections else "left",
                center_vertical=True,
            )
            if heading_text:
                header_draw = ImageDraw.Draw(frame)
                header_draw.text(
                    (content_box[0], label_pos[1]),
                    heading_text,
                    font=label_font,
                    fill=text_color,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_color,
                )
            safe_label = sanitize_filename(label)
            filename = f"{global_index:02d} {safe_label} {current_slide_index}.jpg"
            path = output_dir / filename
            frame.save(path, format="JPEG", quality=92)
            slides.append({"filename": filename, "path": str(path)})
            global_index += 1
            current_slide_index += 1

    return slides
