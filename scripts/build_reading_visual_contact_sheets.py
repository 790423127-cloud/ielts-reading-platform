from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


POSITIONS = ("top", "middle", "bottom")
TITLE_PATTERN = re.compile(
    r"^C(?P<book>\d+)-Test (?P<test>\d+|[A-Z])-(?:Section|Passage) (?P<part>\d+)$"
)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def slug(value: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))


def local_test_token(book: int, source_token: str) -> str:
    if book == 12 and source_token.isdigit():
        return str(int(source_token) - 4)
    return source_token.lower()


def thumbnail(path: Path, width: int, height: int) -> Image.Image:
    with Image.open(path) as source:
        source = source.convert("RGB")
        return ImageOps.pad(source, (width, height), color="white", method=Image.Resampling.LANCZOS)


def build_sheet(
    book: int,
    source_root: Path,
    local_root: Path,
    output_root: Path,
) -> dict[str, object]:
    manifest_path = source_root / f"c{book}-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    titles = manifest["titles"]
    cell_width = 300
    cell_height = 190
    left_margin = 18
    label_height = 42
    row_gap = 12
    header_height = 70
    row_height = label_height + cell_height + row_gap
    sheet = Image.new(
        "RGB",
        (left_margin * 2 + cell_width * 6, header_height + row_height * len(titles)),
        "#f2f4f6",
    )
    draw = ImageDraw.Draw(sheet)
    title_font = font(25)
    label_font = font(18)
    small_font = font(15)
    draw.text((left_margin, 16), f"C{book}: IELTSBro source app vs local implementation", fill="#111827", font=title_font)
    for column, position in enumerate(POSITIONS):
        x = left_margin + column * cell_width * 2
        draw.text((x + 6, 48), f"SOURCE {position.upper()}", fill="#1d4ed8", font=small_font)
        draw.text((x + cell_width + 6, 48), f"LOCAL {position.upper()}", fill="#047857", font=small_font)

    missing: list[str] = []
    for row_index, title in enumerate(titles):
        match = TITLE_PATTERN.match(title)
        if not match:
            missing.append(f"unparsed title: {title}")
            continue
        source_test = match.group("test")
        part = int(match.group("part"))
        local_test = local_test_token(book, source_test)
        source_dir = source_root / slug(title)
        local_prefix = f"b{book}-test-{local_test}-part-{part}"
        y = header_height + row_index * row_height
        draw.rectangle((0, y, sheet.width, y + row_height - row_gap), fill="white")
        draw.text(
            (left_margin, y + 8),
            f"{title}  ->  b{book}-test-{local_test} / Part {part}",
            fill="#111827",
            font=label_font,
        )
        image_y = y + label_height
        for position_index, position in enumerate(POSITIONS):
            source_path = source_dir / f"{position}.png"
            local_path = local_root / f"{local_prefix}-{position}.jpg"
            for side_index, image_path in enumerate((source_path, local_path)):
                x = left_margin + (position_index * 2 + side_index) * cell_width
                if not image_path.is_file():
                    missing.append(str(image_path))
                    draw.rectangle((x, image_y, x + cell_width, image_y + cell_height), outline="#dc2626", width=3)
                    draw.text((x + 8, image_y + 8), "MISSING", fill="#dc2626", font=label_font)
                    continue
                sheet.paste(thumbnail(image_path, cell_width, cell_height), (x, image_y))
                draw.rectangle((x, image_y, x + cell_width - 1, image_y + cell_height - 1), outline="#cbd5e1")

    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"c{book}-source-vs-local.jpg"
    sheet.save(output_path, "JPEG", quality=88, optimize=True)
    return {"book": book, "parts": len(titles), "missing": missing, "output": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    results = [
        build_sheet(book, args.source_root, args.local_root, args.output_root)
        for book in range(5, 21)
    ]
    summary = {
        "books": len(results),
        "parts": sum(int(item["parts"]) for item in results),
        "missing": [missing for item in results for missing in item["missing"]],
        "sheets": [item["output"] for item in results],
    }
    (args.output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
