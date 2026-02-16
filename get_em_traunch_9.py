"""
Sequential PDF downloader for DOJ Epstein dataset.
Downloads EFTA00000001.pdf through EFTA00003158.pdf with 2-4s delay between requests.

Requires passing the age/robot verification once in a browser, then reuses cookies:
  python get_em.py --auth     # open browser, you verify, cookies saved
  python get_em.py            # download all (uses saved cookies)

  python get_em.py --verify   # print what we get from the first URL (no auth)
  python get_em.py --no-pause # download with no delay between requests
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import requests

# --- Config (edit as needed) ---
BASE_URL = "https://www.justice.gov/epstein/files/DataSet%209/"
START_INDEX = 475860 #475386 #474770 #40277 #39789 #39313 #474309 #39025 
END_INDEX = 1262781  # inclusive
OUTPUT_DIR = Path("downloads_9th_batch")
COOKIES_FILE = Path("cookies.json")
DELAY_MIN = 2
DELAY_MAX = 4
RUN_TIMEOUT_SECONDS = 300  # 5 minutes; main download loop exits after this

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _first_url() -> str:
    return BASE_URL.rstrip("/") + "/" + f"EFTA{START_INDEX:08d}.pdf"


def verify_response() -> None:
    """Fetch the first URL and print status, headers, and body sample (no cookies)."""
    url = _first_url()
    print(f"GET {url}\n", file=sys.stderr)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    r = session.get(url, timeout=30)
    print(f"Status: {r.status_code}", file=sys.stderr)
    print(f"Content-Type: {r.headers.get('Content-Type', '(none)')}", file=sys.stderr)
    print("Headers:", file=sys.stderr)
    for k, v in r.headers.items():
        print(f"  {k}: {v}", file=sys.stderr)
    body = r.content[:500]
    print(f"\nFirst 500 bytes (repr): {body!r}", file=sys.stderr)
    print(f"\nStarts with %PDF: {body.startswith(b'%PDF')}", file=sys.stderr)


def run_auth_browser() -> None:
    """Open browser to first PDF URL; after you verify, save cookies to COOKIES_FILE."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)
    url = _first_url()
    print(f"Opening browser to: {url}", file=sys.stderr)
    print("Complete the 'I am not a robot' and age verification, then come back here.", file=sys.stderr)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        input("Press Enter here after you've verified (robot + age) in the browser... ")
        cookies = context.cookies()
        browser.close()
    saved = [{"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path", "/")} for c in cookies]
    COOKIES_FILE.write_text(json.dumps(saved, indent=2))
    print(f"Saved {len(saved)} cookies to {COOKIES_FILE}", file=sys.stderr)


def load_cookies(session: requests.Session) -> None:
    """Load cookies from COOKIES_FILE into the session."""
    if not COOKIES_FILE.exists():
        return
    data = json.loads(COOKIES_FILE.read_text())
    for c in data:
        session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))


# ~3 KB: treat as "small stub" range (2.5 KB–4 KB)
NO_IMAGES_PDF_SIZE_MIN = 2 * 1024   # 2 KB
NO_IMAGES_PDF_SIZE_MAX = 4 * 1024   # 4 KB
NO_IMAGES_PHRASE = "No Images Produced"


def _is_no_images_stub_pdf(path: Path) -> bool:
    """True if PDF is ~3kb and contains 'No Images Produced'."""
    if not path.is_file():
        return False
    size = path.stat().st_size
    if not (NO_IMAGES_PDF_SIZE_MIN <= size <= NO_IMAGES_PDF_SIZE_MAX):
        return False
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        try:
            text = "".join(page.get_text() for page in doc)
            return NO_IMAGES_PHRASE in text
        finally:
            doc.close()
    except Exception:
        return False


def main(*, no_pause: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    load_cookies(session)
    if not COOKIES_FILE.exists():
        print("No cookies.json found. Run: python get_em.py --auth (then verify in browser) first.", file=sys.stderr)

    total = END_INDEX - START_INDEX + 1
    success_count = 0
    failed: list[tuple[int, str]] = []
    start = time.time()

    for i in range(START_INDEX, END_INDEX + 1):
        if (time.time() - start) >= RUN_TIMEOUT_SECONDS:
            print(f"\n5 minute limit reached. Stopping. ({success_count}/{total} succeeded so far)", file=sys.stderr)
            break
        filename = f"EFTA{i:08d}.pdf"
        url = BASE_URL.rstrip("/") + "/" + filename
        out_path = OUTPUT_DIR / filename

        if out_path.exists():
            print(f"[{i - START_INDEX + 1}/{total}] Skip (exists): {filename}", file=sys.stderr)
            success_count += 1
            continue

        try:
            r = session.get(url, stream=True, timeout=60)
            r.raise_for_status()
            # Peek first chunk: real PDFs start with b'%PDF'
            first_chunk = next(r.iter_content(chunk_size=8192), b"")
            if not first_chunk.startswith(b"%PDF"):
                content_type = r.headers.get("Content-Type", "")
                failed.append((i, f"not a PDF (Content-Type: {content_type}, first bytes: {first_chunk[:50]!r})"))
                print(f"[{i - START_INDEX + 1}/{total}] Not a PDF (likely HTML/error page): {filename}", file=sys.stderr)
                if not no_pause:
                    _pause()
                continue
            with open(out_path, "wb") as f:
                f.write(first_chunk)
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            success_count += 1
            print(f"[{success_count}/{total}] Downloaded: {filename}", file=sys.stderr)

            # If PDF is ~3kb and says "No Images Produced", try same base with .mp4
            if _is_no_images_stub_pdf(out_path):
                mp4_filename = f"EFTA{i:08d}.mp4"
                mp4_url = BASE_URL.rstrip("/") + "/" + mp4_filename
                mp4_path = OUTPUT_DIR / mp4_filename
                if not mp4_path.exists():
                    if not no_pause:
                        _pause()
                    try:
                        r_mp4 = session.get(mp4_url, stream=True, timeout=60)
                        r_mp4.raise_for_status()
                        # Require some minimal size so we don't save error pages
                        first_mp4 = next(r_mp4.iter_content(chunk_size=8192), b"")
                        if len(first_mp4) > 1024:  # assume real video has body
                            with open(mp4_path, "wb") as f:
                                f.write(first_mp4)
                                for chunk in r_mp4.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            print(f"  -> Also saved (no-images stub): {mp4_filename}", file=sys.stderr)
                        else:
                            print(f"  -> MP4 attempt for {mp4_filename}: response too small, skipped", file=sys.stderr)
                    except requests.RequestException as e_mp4:
                        print(f"  -> MP4 attempt for {mp4_filename}: {e_mp4}", file=sys.stderr)
        except requests.RequestException as e:
            failed.append((i, str(e)))
            print(f"[{i - START_INDEX + 1}/{total}] Failed {filename}: {e}", file=sys.stderr)

        if not no_pause:
            _pause()

    if failed:
        print(f"\nFailed ({len(failed)}):", file=sys.stderr)
        for idx, err in failed:
            print(f"  EFTA{idx:08d}.pdf: {err}", file=sys.stderr)
    print(f"\nDone. {success_count}/{total} succeeded.", file=sys.stderr)


def _pause() -> None:
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download EFTA PDFs from justice.gov")
    parser.add_argument("--verify", action="store_true", help="Print response from first URL (no cookies)")
    parser.add_argument("--auth", action="store_true", help="Open browser to verify once; save cookies for downloads")
    parser.add_argument("--no-pause", action="store_true", help="No delay between requests")
    args = parser.parse_args()
    if args.verify:
        verify_response()
    elif args.auth:
        run_auth_browser()
    else:
        main(no_pause=args.no_pause)
