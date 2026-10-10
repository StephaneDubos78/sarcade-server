"""Downloads the SARCADE web client into the image (Docker build step).

Non-fatal: without network or release, the image still builds and the
server simply does not serve the web client (the API is unaffected).
"""
import io
import sys
import tarfile
import urllib.request
from pathlib import Path


def main(url: str, target: str) -> int:
    if not url:
        print("web client: no URL, skipped")
        return 0
    dest = Path(target)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            dest.mkdir(parents=True, exist_ok=True)
            archive.extractall(dest, filter="data")
    except Exception as exc:  # noqa: BLE001 - any failure leaves the API usable
        print(f"web client: not embedded ({exc})")
        return 0
    if not (dest / "index.html").is_file():
        print("web client: archive has no index.html, not served")
        return 0
    print(f"web client: embedded in {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2] if len(sys.argv) > 2 else "/app/web"))
