"""
Analyze a PDF for black-box redactions and optionally remove them.

Black-box redactions are black rectangles drawn over text. If the underlying
text was never removed from the PDF, it can still be extracted or revealed by
removing the black rectangles (so-called "fake" or improper redactions).

Usage:
  python analyze_redactions.py path/to/file.pdf
  python analyze_redactions.py path/to/file.pdf --remove -o path/to/output.pdf
"""

import argparse
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF is required. Install with: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

# RGB black (and near-black tolerance)
BLACK = (0.0, 0.0, 0.0)
BLACK_TOLERANCE = 0.05  # treat as black if all components <= this
MIN_RECT_SIZE = 3  # ignore tiny rects (e.g. rules/dots)


def _is_black_fill(fill) -> bool:
    if fill is None:
        return False
    if isinstance(fill, (list, tuple)) and len(fill) >= 3:
        r, g, b = fill[0], fill[1], fill[2]
        return r <= BLACK_TOLERANCE and g <= BLACK_TOLERANCE and b <= BLACK_TOLERANCE
    return False


def find_black_rects(page: "fitz.Page") -> list[tuple["fitz.Rect", int]]:
    """Return list of (rect, seqno) for black filled rectangles on the page."""
    candidates = []
    for path in page.get_drawings():
        # Skip stroke-only (no fill)
        if path.get("type") == "s":
            continue
        if path.get("fill_opacity", 1) != 1:
            continue
        fill = path.get("fill")
        if not _is_black_fill(fill):
            continue
        seqno = path.get("seqno", -1)
        for item in path.get("items", []):
            if not (isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == "re"):
                continue
            rect = item[1]
            if not hasattr(rect, "width"):
                rect = fitz.Rect(rect)
            if rect.width <= MIN_RECT_SIZE or rect.height <= MIN_RECT_SIZE:
                continue
            candidates.append((rect, seqno))
    return candidates


def find_hidden_text(page: "fitz.Page", black_rects: list[tuple]) -> list[dict]:
    """For each black rect, find text drawn before it (potential hidden content)."""
    try:
        trace = list(page.get_texttrace())
    except (AttributeError, Exception):
        return [{"rect": r, "seqno": sn, "hidden_preview": None} for r, sn in black_rects]
    # Build list of (char, bbox_rect, seqno)
    chars = []
    for span in trace:
        seqno = span.get("seqno", -1)
        for char_item in span.get("chars", []):
            try:
                c, _x, _o, b = char_item[:4]
            except (TypeError, IndexError):
                continue
            ch = chr(c) if isinstance(c, int) else c
            if not ch.isalnum() and ch not in " .-_":
                continue
            try:
                bbox = fitz.Rect(b) if not isinstance(b, fitz.Rect) else b
            except Exception:
                continue
            chars.append((ch, bbox, seqno))

    results = []
    for rect, rect_seqno in black_rects:
        covered = [
            c for c, bbox, seqno in chars
            if bbox.intersects(rect) and seqno < rect_seqno
        ]
        if covered:
            results.append({"rect": rect, "seqno": rect_seqno, "hidden_preview": "".join(covered)})
        else:
            results.append({"rect": rect, "seqno": rect_seqno, "hidden_preview": None})
    return results


def analyze_pdf(path: Path) -> dict:
    """Open PDF and return analysis: per-page black rects, hidden text, and full page text."""
    doc = fitz.open(path)
    report = {"path": str(path), "pages": [], "total_black_rects": 0, "full_text": []}
    try:
        for page in doc:
            pno = page.number
            black_rects = find_black_rects(page)
            hidden = find_hidden_text(page, black_rects) if black_rects else []
            page_text = page.get_text()
            report["full_text"].append({"page": pno + 1, "text": page_text})
            if black_rects:
                report["pages"].append({
                    "page": pno + 1,
                    "black_rects": black_rects,
                    "hidden": hidden,
                })
                report["total_black_rects"] += len(black_rects)
    finally:
        doc.close()
    return report


def remove_black_rects(path: Path, output_path: Path) -> tuple[int, list[str]]:
    """
    Add redaction annotations on black rectangles and apply redactions so that
    only the drawing (black box) is removed; text in that area is kept.
    Returns (count_removed, list of error/warning messages).
    """
    doc = fitz.open(path)
    messages = []
    total_removed = 0
    try:
        for page in doc:
            black_rects = find_black_rects(page)
            for rect, _seqno in black_rects:
                # fill=False so we don't draw a white box; we only remove the drawing
                page.add_redact_annot(rect, fill=False)
                total_removed += 1
            if black_rects:
                # Remove only graphics (line art), keep text and don't touch images
                applied = page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                    text=fitz.PDF_REDACT_TEXT_NONE,
                )
                if not applied and black_rects:
                    messages.append(f"Page {page.number + 1}: redactions may not have been applied")
        doc.save(output_path, garbage=4, deflate=True)
    except Exception as e:
        messages.append(str(e))
    finally:
        doc.close()
    return total_removed, messages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a PDF for black-box redactions and optionally remove them."
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the PDF file")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove black-box redactions (writes new PDF; keeps underlying text)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output path when using --remove (default: input_unredacted.pdf)",
    )
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        print(f"Error: file not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    if args.remove:
        out = args.output or args.pdf_path.with_stem(args.pdf_path.stem + "_unredacted")
        count, msgs = remove_black_rects(args.pdf_path, out)
        for m in msgs:
            print(m, file=sys.stderr)
        print(f"Removed {count} black box redaction(s). Saved to: {out}")
        return

    report = analyze_pdf(args.pdf_path)
    print(f"File: {report['path']}")

    if not report["pages"]:
        print("No black-box redactions detected.\n")
        print("=" * 60)
        print("FULL DOCUMENT TEXT (all pages)")
        print("=" * 60)
        for pt in report["full_text"]:
            print(f"\n--- Page {pt['page']} ---")
            print(pt["text"] if pt["text"].strip() else "(no text)")
        return

    print()
    print(f"Total black rectangles (potential redactions): {report['total_black_rects']}\n")

    # --- Text pulled out from under redactions (full text, no truncation) ---
    print("=" * 60)
    print("EXTRACTED TEXT FROM UNDER REDACTIONS")
    print("=" * 60)
    for p in report["pages"]:
        print(f"\n  Page {p['page']} ({len(p['black_rects'])} redaction(s)):")
        for i, h in enumerate(p["hidden"]):
            r = h["rect"]
            text = h.get("hidden_preview")
            print(f"    Rect {i + 1} at ({r.x0:.0f},{r.y0:.0f})-({r.x1:.0f},{r.y1:.0f}):")
            if text:
                for line in text.splitlines():
                    print(f"      {line}")
                if not text.endswith("\n"):
                    print()
            else:
                print("      (no text detected under this rect)")
    print()

    # --- Full document text (all pages) ---
    print("=" * 60)
    print("FULL DOCUMENT TEXT (all pages)")
    print("=" * 60)
    for pt in report["full_text"]:
        print(f"\n--- Page {pt['page']} ---")
        print(pt["text"] if pt["text"].strip() else "(no text)")
    print()

    print("To remove these redactions and reveal underlying text in the PDF, run:")
    print(f"  python analyze_redactions.py \"{report['path']}\" --remove -o output.pdf")


if __name__ == "__main__":
    main()
