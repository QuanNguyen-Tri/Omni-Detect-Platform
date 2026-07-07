#!/usr/bin/env python3
"""
prepare_inputs.py — normalize ANY of these into a flat list of absolute image
paths (and, optionally, a `.jsonl` list file that inference.py / infer_lisa.py
can consume directly):

  * a single image file            (foo.png)
  * a directory of images          (recursively globbed, sorted)
  * a text list                    (.txt — one path per line, '#' comments ok)
  * a JSON list / object           (.json — [..] or {"images":[..]} / {"image_paths":[..]})
  * a JSON-lines file              (.jsonl — one string or {"image_path":..} per line)
  * a CSV                          (.csv — image column auto-detected, else first column)

This is the piece the repo's own `inference.py` lacks (it takes only explicit
paths or a .txt/.json/.jsonl list — no folder scan, no CSV). Everything else in
the toolkit funnels its input through here so single vs. batch is uniform.

Standalone:
    python prepare_inputs.py --input some_dir/           --out list.jsonl
    python prepare_inputs.py --input batch.csv           --out list.jsonl
    python prepare_inputs.py --input one.png                        # just prints the resolved path
"""

import argparse
import csv
import json
import os
import sys

IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")

# CSV / JSON column names that we treat as "this holds an image path".
_PATH_KEYS = (
    "image_path", "file_path", "filepath", "image_file", "img_path",
    "path", "file", "image", "img", "filename",
)


def _looks_like_image(p):
    return str(p).strip().lower().endswith(IMG_EXTS)


def _abs(p, base_dir):
    """Resolve one path token to an absolute path.

    Tries, in order: as-is (if absolute), relative to CWD, relative to the list
    file's own directory. Falls back to CWD-relative so a missing file still
    yields a stable, reportable absolute path.
    """
    p = os.path.expanduser(str(p).strip())
    if not p:
        return None
    if os.path.isabs(p):
        return os.path.abspath(p)
    c_cwd = os.path.abspath(p)
    if os.path.exists(c_cwd):
        return c_cwd
    if base_dir:
        c_base = os.path.abspath(os.path.join(base_dir, p))
        if os.path.exists(c_base):
            return c_base
    return c_cwd


def _item_to_path(item):
    """Pull a path out of a str or a dict (json/jsonl element)."""
    if isinstance(item, dict):
        for k in _PATH_KEYS:
            if k in item and item[k]:
                return item[k]
        return None
    return item


def _from_directory(d):
    out = []
    for root, _dirs, files in os.walk(d):
        for name in files:
            if name.lower().endswith(IMG_EXTS):
                out.append(os.path.abspath(os.path.join(root, name)))
    return sorted(out)


def _from_txt(path, base):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(_abs(line, base))
    return out


def _from_json(path, base):
    text = open(path, encoding="utf-8").read()
    if not text.strip():                       # empty file -> [] (like txt/csv/jsonl)
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON in {path}: {e}") from e
    if isinstance(data, dict):
        data = data.get("images") or data.get("image_paths") or data.get("data") or []
    if isinstance(data, str):                  # a single path given as a bare string
        data = [data]
    if not isinstance(data, (list, tuple)):
        raise ValueError(
            f"unsupported JSON in {path}: expected a list, a bare string, "
            f"or {{'images': [...]}} — got {type(data).__name__}")
    out = []
    for item in data:
        p = _item_to_path(item)
        if p:
            out.append(_abs(p, base))
    return out


def _from_jsonl(path, base):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = _item_to_path(json.loads(line))
            if p:
                out.append(_abs(p, base))
    return out


def _from_csv(path, base):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    col = next((i for i, h in enumerate(header) if h in _PATH_KEYS), None)
    if col is not None:                       # named image column -> skip header row
        start = 1
    else:                                     # no named column: use col 0
        col = 0
        # keep row 0 only if it already looks like a path (headerless CSV)
        start = 0 if (rows[0] and _looks_like_image(rows[0][0])) else 1
    out = []
    for r in rows[start:]:
        if col < len(r) and r[col].strip():
            out.append(_abs(r[col], base))
    return out


def resolve_inputs(input_path):
    """Return a deduplicated, order-preserving list of absolute image paths."""
    input_path = os.path.expanduser(input_path)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"--input not found: {input_path}")

    if os.path.isdir(input_path):
        paths = _from_directory(input_path)
    else:
        base = os.path.dirname(os.path.abspath(input_path))
        ext = os.path.splitext(input_path)[1].lower()
        if ext in IMG_EXTS:
            paths = [os.path.abspath(input_path)]
        elif ext == ".txt":
            paths = _from_txt(input_path, base)
        elif ext == ".json":
            paths = _from_json(input_path, base)
        elif ext == ".jsonl":
            paths = _from_jsonl(input_path, base)
        elif ext == ".csv":
            paths = _from_csv(input_path, base)
        else:
            # Unknown extension: try to read it as a newline-delimited path list.
            paths = _from_txt(input_path, base)

    seen, out = set(), []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def read_image_list_file(list_path):
    """Read a normalized .jsonl/.json/.txt path list (used by the workers)."""
    return resolve_inputs(list_path)


def write_jsonl(paths, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(json.dumps({"image_path": p}, ensure_ascii=False) + "\n")
    return out_path


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="image | folder | .txt/.json/.jsonl/.csv")
    ap.add_argument("--out", default=None, help="write a normalized .jsonl here")
    ap.add_argument("--limit", type=int, default=None, help="keep only the first N images")
    args = ap.parse_args(argv)

    paths = resolve_inputs(args.input)
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]

    missing = [p for p in paths if not os.path.exists(p)]
    print(f"resolved {len(paths)} image path(s) from {args.input}", file=sys.stderr)
    if missing:
        print(f"  WARNING: {len(missing)} path(s) do not exist on disk (first: {missing[0]})",
              file=sys.stderr)

    if args.out:
        write_jsonl(paths, args.out)
        print(f"wrote {len(paths)} entries -> {args.out}", file=sys.stderr)
    else:
        for p in paths:
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
