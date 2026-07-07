#!/usr/bin/env python3
"""
run.py — unified single/batch inference across the PIXAR / SIDA / LISA baselines.

Takes ONE input (a single image, a folder, or a .txt/.json/.jsonl/.csv list),
runs each requested model, and writes a combined, granularity-labelled summary.

  * PIXAR-7B / PIXAR-13B / SIDA-7B / SIDA-13B
        -> driven through the release repo's proven `pixel-tampering-dg/inference.py`
           (SIDA loads via the same PIXARForCausalLM class; its [OBJ] head is not
           meaningful, so object-level output is suppressed for SIDA).
  * LISA-7B / LISA-13B
        -> driven through this toolkit's `infer_lisa.py` (segmentation-only).

Output granularities (the "key outputs"):
  document-level  -> [CLS] real/tampered   (LISA: derived from the mask)
  object-level    -> [OBJ] top object cats (PIXAR only; SIDA/LISA: n/a)
  pixel-level     -> [SEG] tampering mask   + overlay + positive-pixel fraction
  (plus the model's free-text description)

Examples:
  # single image, all three families
  python run.py --input img.png --output_dir out --gpu 0

  # batch over a folder, only PIXAR-7B + LISA-7B
  python run.py --input images_dir/ --models PIXAR-7B LISA-7B --output_dir out --gpu 0

  # batch from a CSV, show the exact commands without running (no GPU needed)
  python run.py --input batch.csv --output_dir out --dry-run
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, ".."))
PIXAR_DIR = os.path.join(REPO_ROOT, "pixel-tampering-dg")
DEFAULT_PYTHON = "/home/omnidet/miniconda3/envs/pixar/bin/python"

# name -> (family, checkpoint subdir under --pretrains, object-head reliable?)
REGISTRY = {
    "PIXAR-7B":  ("pixar", "PIXAR-7B",  True),
    "PIXAR-13B": ("pixar", "PIXAR-13B", True),
    "SIDA-7B":   ("pixar", "SIDA-7B",   False),   # no [OBJ] token -> obj output ignored
    "SIDA-13B":  ("pixar", "SIDA-13B",  False),
    "LISA-7B":   ("lisa",  "LISA-7B",   False),   # seg-only, no [CLS]/[OBJ]
    "LISA-13B":  ("lisa",  "LISA-13B",  False),
}
DEFAULT_MODELS = ["PIXAR-7B", "SIDA-7B", "LISA-7B"]


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="image | folder | .txt/.json/.jsonl/.csv list")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                    choices=list(REGISTRY.keys()),
                    help=f"baselines to run (default: {' '.join(DEFAULT_MODELS)})")
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--gpu", default="0", help="single GPU id for all models")
    ap.add_argument("--pretrains", default=os.path.join(REPO_ROOT, "pretrains"),
                    help="dir holding PIXAR-*/SIDA-*/LISA-*/sam_vit_h_4b8939.pth")
    ap.add_argument("--python", default=DEFAULT_PYTHON if os.path.exists(DEFAULT_PYTHON)
                    else sys.executable, help="python interpreter (the 'pixar' conda env)")
    ap.add_argument("--precision", default="bf16", choices=["fp32", "bf16", "fp16"])
    ap.add_argument("--max_new_tokens", type=int, default=128)
    ap.add_argument("--mask_threshold", type=float, default=0.5)
    ap.add_argument("--seg_prompt_mode", default="fuse", choices=["seg_only", "text_only", "fuse"])
    ap.add_argument("--obj_top_k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None, help="cap number of images (smoke test)")
    ap.add_argument("--load_in_8bit", action="store_true")
    ap.add_argument("--load_in_4bit", action="store_true")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="print the per-model commands without executing")
    return ap.parse_args(argv)


def build_pixar_cmd(args, ckpt, out_dir, jsonl):
    sam = os.path.join(args.pretrains, "sam_vit_h_4b8939.pth")
    cmd = [args.python, "inference.py",
           "--version", ckpt,
           "--vision_pretrained", sam,
           "--seg_prompt_mode", args.seg_prompt_mode,
           "--image_list", jsonl,
           "--output_dir", out_dir,
           "--precision", args.precision,
           "--mask_threshold", str(args.mask_threshold),
           "--obj_top_k", str(args.obj_top_k),
           "--max_new_tokens", str(args.max_new_tokens),
           "--no-copy_gt_mask"]
    if args.load_in_8bit:
        cmd.append("--load_in_8bit")
    if args.load_in_4bit:
        cmd.append("--load_in_4bit")
    return cmd, PIXAR_DIR


def build_lisa_cmd(args, ckpt, out_dir, jsonl):
    cmd = [args.python, os.path.join(HERE, "infer_lisa.py"),
           "--version", ckpt,
           "--image_list", jsonl,
           "--output_dir", out_dir,
           "--gpu", str(args.gpu),
           "--precision", args.precision,
           "--mask_threshold", str(args.mask_threshold),
           "--max_new_tokens", str(args.max_new_tokens)]
    if args.load_in_8bit:
        cmd.append("--load_in_8bit")
    if args.load_in_4bit:
        cmd.append("--load_in_4bit")
    return cmd, HERE


def fold_result(model, obj_reliable, r):
    """Normalize one inference.py / infer_lisa.py result into a common record."""
    cls = r.get("cls_head") or {}
    probs = cls.get("probabilities", {})
    loc = r.get("localization") or {}
    obj = None
    note = None
    if r.get("obj_head") and obj_reliable:
        obj = [{"name": o["name"], "prob": round(float(o["probability"]), 4)}
               for o in r["obj_head"].get("top_k", [])]
    elif r.get("obj_head") and not obj_reliable:
        note = "object-level suppressed (no reliable [OBJ] head for this model)"
    return {
        "model": model,
        "image_path": r.get("image_path"),
        "document_level": {
            "label": cls.get("predicted_label"),
            "p_real": round(float(probs.get("real", 0.0)), 4),
            "p_tampered": round(float(probs.get("tampered", 0.0)), 4),
            "source": cls.get("source", "[CLS] head"),
        } if cls else None,
        "object_level": obj,
        "object_level_note": note,
        "pixel_level": {
            "overlay_png": loc.get("overlay_png"),
            "mask_png": loc.get("mask_png"),
            "positive_pixel_fraction": loc.get("positive_pixel_fraction"),
        } if loc else None,
        "text": r.get("text", ""),
    }


def main(argv):
    args = parse_args(argv)
    # Absolute-ize so the parent's isdir() guard and the child (which runs with
    # cwd=pixel-tampering-dg) resolve checkpoints against the SAME base dir.
    args.pretrains = os.path.abspath(os.path.expanduser(args.pretrains))
    out_root = os.path.abspath(args.output_dir)
    os.makedirs(out_root, exist_ok=True)

    # 1) Normalize the input to one jsonl the workers share.
    sys.path.insert(0, HERE)
    import prepare_inputs
    paths = prepare_inputs.resolve_inputs(args.input)
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]
    if not paths:
        print("ERROR: no images resolved from --input", file=sys.stderr)
        return 2
    jsonl = os.path.join(out_root, "_inputs.jsonl")
    prepare_inputs.write_jsonl(paths, jsonl)
    missing = [p for p in paths if not os.path.exists(p)]
    print(f"[inputs] {len(paths)} image(s) -> {jsonl}"
          + (f"  ({len(missing)} MISSING on disk!)" if missing else ""))

    # 2) Run each model.
    all_records, statuses = [], []
    for model in args.models:
        family, subdir, obj_reliable = REGISTRY[model]
        ckpt = os.path.join(args.pretrains, subdir)
        out_dir = os.path.join(out_root, model)
        os.makedirs(out_dir, exist_ok=True)

        env = dict(os.environ)
        if family == "pixar":
            cmd, cwd = build_pixar_cmd(args, ckpt, out_dir, jsonl)
            # inference.py has no --gpu flag, so pin the device via the env.
            env["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
        else:
            cmd, cwd = build_lisa_cmd(args, ckpt, out_dir, jsonl)
            # infer_lisa.py sets CUDA_VISIBLE_DEVICES itself from --gpu; do NOT
            # pre-mask here or the child would re-index an already-masked world.
            env.pop("CUDA_VISIBLE_DEVICES", None)

        print(f"\n=== {model} ({family}) ===")
        print(f"  ckpt : {ckpt}" + ("   [MISSING — run baselines/setup.sh]"
                                    if not os.path.isdir(ckpt) else ""))
        print(f"  cwd  : {cwd}")
        print(f"  cmd  : {' '.join(cmd)}")

        if args.dry_run:
            statuses.append({"model": model, "status": "dry-run"})
            continue
        if not os.path.isdir(ckpt):
            print(f"  SKIP: checkpoint not found. Download it with: bash {HERE}/setup.sh --models {model}")
            statuses.append({"model": model, "status": "skipped-missing-ckpt"})
            continue

        rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
        statuses.append({"model": model, "status": "ok" if rc == 0 else f"exit={rc}"})
        summ = os.path.join(out_dir, "summary.json")
        if rc == 0 and os.path.isfile(summ):
            for r in json.load(open(summ, encoding="utf-8")):
                all_records.append(fold_result(model, obj_reliable, r))

    if args.dry_run:
        print("\n[dry-run] no models executed.")
        return 0

    # 3) Combined outputs.
    combined = os.path.join(out_root, "summary_all.json")
    json.dump({"statuses": statuses, "results": all_records},
              open(combined, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    import csv
    with open(os.path.join(out_root, "summary_all.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "image_path", "doc_label", "p_tampered",
                    "top_object", "top_object_prob", "pos_pixel_frac"])
        for r in all_records:
            doc = r.get("document_level") or {}
            obj = (r.get("object_level") or [{}])[0] if r.get("object_level") else {}
            px = r.get("pixel_level") or {}
            w.writerow([r["model"], r["image_path"], doc.get("label"), doc.get("p_tampered"),
                        obj.get("name", ""), obj.get("prob", ""),
                        px.get("positive_pixel_fraction")])

    # 4) Console table.
    print("\n" + "=" * 92)
    print(f"{'model':<10} {'doc':<9} {'p_tamp':>7} {'top_object':<14} {'pos_pix%':>8}  image")
    print("-" * 92)
    for r in all_records:
        doc = r.get("document_level") or {}
        obj = (r.get("object_level") or [{}])[0] if r.get("object_level") else {}
        px = r.get("pixel_level") or {}
        ppf = px.get("positive_pixel_fraction")
        print(f"{r['model']:<10} {str(doc.get('label')):<9} {doc.get('p_tampered', ''):>7} "
              f"{obj.get('name', '-'):<14} "
              f"{(f'{ppf*100:.2f}' if isinstance(ppf, (int, float)) else '-'):>8}  "
              f"{os.path.basename(str(r['image_path']))}")
    print("=" * 92)
    print(f"statuses: {statuses}")
    print(f"combined -> {combined}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
