"""Concatenate the vendored CodeMirror files into one bundle so the workstation
loads a single script instead of sixteen.

    python tools/bundle_vendor.py            # (re)write the bundle + manifest
    python tools/bundle_vendor.py --check    # exit 1 when the bundle is stale

The manifest records the sha256 of every part; the smoke suite runs --check so
a changed part without a rebuilt bundle fails CI. Order matters: the core first,
then modes, then addons (htmlmixed needs xml/javascript/css before it).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "sim" / "adapters" / "web" / "static" / "vendor" / "codemirror"
BUNDLE = VENDOR / "bundle.min.js"
MANIFEST = VENDOR / "bundle.manifest.json"
PARTS = [
    "codemirror.min.js",
    "mode/xml.min.js", "mode/javascript.min.js", "mode/css.min.js", "mode/htmlmixed.min.js",
    "mode/markdown.min.js", "mode/python.min.js", "mode/yaml.min.js", "mode/sql.min.js",
    "mode/shell.min.js",
    "addon/active-line.min.js", "addon/matchbrackets.min.js", "addon/closebrackets.min.js",
    "addon/searchcursor.min.js", "addon/dialog.min.js", "addon/search.min.js",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> tuple[bytes, dict]:
    chunks, manifest = [], {"parts": []}
    for rel in PARTS:
        data = (VENDOR / rel).read_bytes()
        manifest["parts"].append({"path": rel, "sha256": _sha(data), "bytes": len(data)})
        chunks.append(f"/* ---- {rel} ---- */\n".encode() + data.rstrip(b"\n") + b"\n;\n")
    bundle = b"".join(chunks)
    manifest["bundle_sha256"] = _sha(bundle)
    return bundle, manifest


def is_current() -> bool:
    if not BUNDLE.exists() or not MANIFEST.exists():
        return False
    try:
        want = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except ValueError:
        return False
    bundle, manifest = build()
    return want == manifest and _sha(BUNDLE.read_bytes()) == manifest["bundle_sha256"]


def write() -> None:
    bundle, manifest = build()
    BUNDLE.write_bytes(bundle)
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        if is_current():
            print("vendor bundle is current")
            return 0
        print("vendor bundle is stale: run python tools/bundle_vendor.py", file=sys.stderr)
        return 1
    write()
    print(f"wrote {BUNDLE.relative_to(ROOT)} ({BUNDLE.stat().st_size // 1024} KB, {len(PARTS)} parts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
