#!/usr/bin/env python3
"""Convert existing media images to WebP format.

Usage:
    python -m transversal.convert_media [--dir /app/media] [--quality 85] [--dry-run]

Converts PNG, JPG, JPEG images to WebP. Skips SVG and GIF files.
Existing .webp files are skipped. Original files are NOT deleted.
"""

import argparse
import io
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


def convert_file(filepath: Path, quality: int = 85, dry_run: bool = False) -> tuple[str, int, int]:
    """Convert a single image file to WebP. Returns (status, orig_size, new_size)."""
    ext = filepath.suffix.lower()
    if ext == ".webp":
        return ("skip-already-webp", 0, 0)
    if ext in (".svg", ".gif"):
        return ("skip-unsupported", 0, 0)

    try:
        orig_size = filepath.stat().st_size
        img = Image.open(filepath)

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        out_path = filepath.with_suffix(".webp")
        if dry_run:
            return ("dry-run", orig_size, 0)

        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality)
        new_data = buf.getvalue()

        out_path.write_bytes(new_data)
        new_size = len(new_data)
        savings = orig_size - new_size
        pct = (savings / orig_size * 100) if orig_size > 0 else 0
        status = f"converted ({pct:+.0f}%, {orig_size} → {new_size} bytes)"
        return (status, orig_size, new_size)

    except Exception as e:
        return (f"error: {e}", 0, 0)


def main():
    parser = argparse.ArgumentParser(description="Convert media images to WebP")
    parser.add_argument("--dir", default="/app/media", help="Media directory (default: /app/media)")
    parser.add_argument("--quality", type=int, default=85, help="WebP quality 0-100 (default: 85)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be converted without writing")
    args = parser.parse_args()

    media_dir = Path(args.dir)
    if not media_dir.is_dir():
        print(f"Directory not found: {media_dir}")
        sys.exit(1)

    images = sorted(
        [p for p in media_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}],
        key=lambda p: p.name,
    )

    print(f"Found {len(images)} image files in {media_dir}")
    if args.dry_run:
        print("DRY RUN — no files will be modified\n")

    total_orig = 0
    total_new = 0
    converted = 0
    skipped = 0
    errors = 0

    for img_path in images:
        status, orig, new = convert_file(img_path, args.quality, args.dry_run)
        print(f"  {img_path.name}: {status}")

        if status.startswith("converted"):
            converted += 1
            total_orig += orig
            total_new += new
        elif status.startswith("skip"):
            skipped += 1
        else:
            errors += 1

    print(f"\nResults: {converted} converted, {skipped} skipped, {errors} errors")
    if converted > 0:
        savings = total_orig - total_new
        pct = (savings / total_orig * 100) if total_orig > 0 else 0
        print(f"Total size: {total_orig:,} → {total_new:,} bytes ({savings:,} saved, {pct:.0f}%)")


if __name__ == "__main__":
    main()
