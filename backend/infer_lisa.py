#!/usr/bin/env python3
"""
infer_lisa.py — run the LISA baseline on ARBITRARY loose images (single or batch)
and save per-image outputs, with NO ground-truth masks required.

The repo ships `lisa/eval_lisa.py` (scores LISA against GT masks on a PIXAR-format
dataset) and `lisa/chat.py` (interactive one-image REPL), but nothing that just
runs LISA over a folder / list of images the way `pixel-tampering-dg/inference.py`
does for PIXAR. This mirrors `eval_lisa.py`'s proven load + `model.evaluate` path
and writes the same output layout as `inference.py`, so the unified runner can
aggregate all three baselines identically.

LISA is a reasoning-SEGMENTATION model: it has no [CLS]/[OBJ] head. So:
  * pixel-level  -> predicted tampering mask (this is LISA's real output)
  * document-level -> DERIVED from the mask (tampered iff any positive pixel)
  * object-level -> not available (null)
  * text -> the model's free-form generation (optional)

Usage:
    python infer_lisa.py --version pretrains/LISA-7B \
        --input path/to/img_or_folder_or_list --output_dir out/LISA-7B --gpu 0
    python infer_lisa.py --version pretrains/LISA-13B \
        --image_list normalized.jsonl --output_dir out/LISA-13B --gpu 0
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

# Resolve the vendored LISA package (sibling dir `lisa/`), matching eval_lisa.py.
BASELINES_DIR = os.path.dirname(os.path.abspath(__file__))
LISA_ROOT = os.environ.get(
    "LISA_ROOT", os.path.normpath(os.path.join(BASELINES_DIR, "..", "lisa"))
)


def parse_args(argv):
    p = argparse.ArgumentParser(description="LISA loose-image inference")
    p.add_argument("--version", required=True, type=str,
                   help="LISA checkpoint dir or HF id (e.g. pretrains/LISA-7B)")
    p.add_argument("--input", default=None, type=str,
                   help="image | folder | .txt/.json/.jsonl/.csv (via prepare_inputs)")
    p.add_argument("--image_list", default=None, type=str,
                   help="a .jsonl/.json/.txt list of image paths")
    p.add_argument("--image_paths", nargs="*", default=[], help="explicit image paths")
    p.add_argument("--output_dir", required=True, type=str)

    p.add_argument("--gpu", default="0", type=str, help="single GPU id (CUDA_VISIBLE_DEVICES)")
    p.add_argument("--precision", default="bf16", choices=["fp32", "bf16", "fp16"])
    p.add_argument("--image_size", default=1024, type=int)
    p.add_argument("--model_max_length", default=512, type=int)
    p.add_argument("--vision_tower", default="openai/clip-vit-large-patch14", type=str)
    p.add_argument("--load_in_8bit", action="store_true", default=False)
    p.add_argument("--load_in_4bit", action="store_true", default=False)
    p.add_argument("--use_mm_start_end", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--conv_type", default="llava_v1", choices=["llava_v1", "llava_llama_2"])
    p.add_argument("--max_new_tokens", default=64, type=int)
    p.add_argument("--mask_threshold", default=0.5, type=float)
    p.add_argument("--prompt",
                   default="Please segment the manipulated or tampered region in this image.",
                   type=str)
    p.add_argument("--copy_input", action=argparse.BooleanOptionalAction, default=True)
    return p.parse_args(argv)


def gather_paths(args):
    """Collect absolute image paths from --input / --image_list / --image_paths.

    Done BEFORE we chdir into the LISA package so relative paths still resolve.
    """
    sys.path.insert(0, BASELINES_DIR)
    import prepare_inputs  # noqa: E402  (local module)

    paths = []
    for p in (args.image_paths or []):
        paths.extend(prepare_inputs.resolve_inputs(p))
    if args.image_list:
        paths.extend(prepare_inputs.read_image_list_file(args.image_list))
    if args.input:
        paths.extend(prepare_inputs.resolve_inputs(args.input))

    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    if not out:
        raise ValueError("No images provided. Use --input / --image_list / --image_paths.")
    return out


def safe_sample_dir(output_dir, index, image_path):
    stem = Path(image_path).stem
    digest = hashlib.sha1(os.path.abspath(image_path).encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)[:80]
    return output_dir / f"sample_{index:04d}_{safe}_{digest}"


def main(argv):
    args = parse_args(argv)
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    image_paths = gather_paths(args)
    output_dir = Path(os.path.abspath(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    version = args.version
    if not os.path.isabs(version) and os.path.exists(version):
        version = os.path.abspath(version)

    # Enter the LISA package so `model.LISA`, `model.llava.*`, `utils.utils`
    # resolve to the vendored tree (same trick as eval_lisa.py's worker).
    os.chdir(LISA_ROOT)
    if LISA_ROOT not in sys.path:
        sys.path.insert(0, LISA_ROOT)

    import warnings
    warnings.filterwarnings("ignore")

    import cv2
    import numpy as np
    import shutil
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, BitsAndBytesConfig, CLIPImageProcessor

    def imwrite_or_raise(path, arr):
        # cv2.imwrite returns False (does not raise) on write failure; surface it
        # so the per-image except routes this sample into errors.json, not results.
        if not cv2.imwrite(str(path), arr):
            raise IOError(f"cv2.imwrite failed: {path}")

    from model.LISA import LISAForCausalLM
    from model.llava import conversation as conversation_lib
    from model.llava.mm_utils import tokenizer_image_token
    from model.segment_anything.utils.transforms import ResizeLongestSide
    from utils.utils import (DEFAULT_IM_END_TOKEN, DEFAULT_IM_START_TOKEN,
                             DEFAULT_IMAGE_TOKEN, IMAGE_TOKEN_INDEX)

    # ---- tokenizer ----
    tokenizer = AutoTokenizer.from_pretrained(
        version, cache_dir=None, model_max_length=args.model_max_length,
        padding_side="right", use_fast=False,
    )
    tokenizer.pad_token = tokenizer.unk_token
    seg_token_idx = tokenizer("[SEG]", add_special_tokens=False).input_ids[0]
    if args.use_mm_start_end:
        tokenizer.add_tokens([DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN], special_tokens=True)

    # ---- model ----
    torch_dtype = {"fp16": torch.half, "bf16": torch.bfloat16}.get(args.precision, torch.float32)
    kwargs = {"torch_dtype": torch_dtype}
    if args.load_in_4bit:
        kwargs.update({
            "torch_dtype": torch.half, "load_in_4bit": True,
            "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                llm_int8_skip_modules=["visual_model"]),
        })
    elif args.load_in_8bit:
        kwargs.update({
            "torch_dtype": torch.half,
            "quantization_config": BitsAndBytesConfig(
                llm_int8_skip_modules=["visual_model"], load_in_8bit=True),
        })

    print(f"loading LISA from {version} ...", flush=True)
    model = LISAForCausalLM.from_pretrained(
        version, low_cpu_mem_usage=True, vision_tower=args.vision_tower,
        seg_token_idx=seg_token_idx, **kwargs,
    )
    model.config.eos_token_id = tokenizer.eos_token_id
    model.config.bos_token_id = tokenizer.bos_token_id
    model.config.pad_token_id = tokenizer.pad_token_id
    model.get_model().initialize_vision_modules(model.get_model().config)
    model.get_model().get_vision_tower().to(dtype=torch_dtype)

    if args.precision == "bf16":
        model = model.bfloat16().cuda()
    elif args.precision == "fp32":
        model = model.float().cuda()
    elif args.precision == "fp16" and not (args.load_in_4bit or args.load_in_8bit):
        model = model.half().cuda()
    model.get_model().get_vision_tower().to(device="cuda")
    model.eval()

    conversation_lib.default_conversation = conversation_lib.conv_templates[args.conv_type]
    clip_processor = CLIPImageProcessor.from_pretrained(model.config.vision_tower)
    transform = ResizeLongestSide(args.image_size)

    pixel_mean = torch.tensor([123.675, 116.28, 103.53]).view(-1, 1, 1)
    pixel_std = torch.tensor([58.395, 57.12, 57.375]).view(-1, 1, 1)

    def sam_preprocess(x):
        x = (x - pixel_mean) / pixel_std
        h, w = x.shape[-2:]
        return F.pad(x, (0, args.image_size - w, 0, args.image_size - h))

    def build_input_ids():
        conv = conversation_lib.default_conversation.copy()
        conv.messages = []
        prompt = DEFAULT_IMAGE_TOKEN + "\n" + args.prompt
        if args.use_mm_start_end:
            replace = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN
            prompt = prompt.replace(DEFAULT_IMAGE_TOKEN, replace)
        conv.append_message(conv.roles[0], prompt)
        conv.append_message(conv.roles[1], "")
        ids = tokenizer_image_token(conv.get_prompt(), tokenizer, return_tensors="pt")
        return ids.unsqueeze(0).cuda()

    results, errors = [], []
    for index, image_path in enumerate(image_paths, start=1):
        print(f"[{index}/{len(image_paths)}] {image_path}", flush=True)
        try:
            img_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise ValueError(f"Failed to load image: {image_path}")
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            H0, W0 = img_rgb.shape[:2]

            image_clip = clip_processor.preprocess(img_rgb, return_tensors="pt")["pixel_values"][0]
            image_clip = image_clip.unsqueeze(0).cuda()
            sam_np = transform.apply_image(img_rgb)
            resize = sam_np.shape[:2]
            image = sam_preprocess(
                torch.from_numpy(sam_np).permute(2, 0, 1).contiguous().float()
            ).unsqueeze(0).cuda()
            if args.precision == "bf16":
                image_clip, image = image_clip.bfloat16(), image.bfloat16()
            elif args.precision == "fp16":
                image_clip, image = image_clip.half(), image.half()

            input_ids = build_input_ids()
            with torch.no_grad():
                output_ids, pred_masks = model.evaluate(
                    image_clip, image, input_ids, [resize], [(H0, W0)],
                    max_new_tokens=args.max_new_tokens, tokenizer=tokenizer,
                )

            new_tokens = output_ids[0][output_ids[0] != IMAGE_TOKEN_INDEX]
            text_output = tokenizer.decode(new_tokens, skip_special_tokens=True)
            text_output = text_output.replace("\n", " ").replace("  ", " ").strip()

            if len(pred_masks) == 0 or pred_masks[0].shape[0] == 0:
                prob = np.zeros((H0, W0), dtype=np.float32)   # no [SEG] -> empty mask
            else:
                logits = pred_masks[0][0].detach().float().cpu()
                prob = torch.sigmoid(logits).numpy() if (logits.min() < 0 or logits.max() > 1.0) \
                    else np.clip(logits.numpy(), 0.0, 1.0)
            binary = prob >= args.mask_threshold

            sample_dir = safe_sample_dir(output_dir, index, image_path)
            sample_dir.mkdir(parents=True, exist_ok=True)
            imwrite_or_raise(sample_dir / "input.png", img_bgr)
            if args.copy_input:
                try:
                    shutil.copy2(image_path, sample_dir / ("source" + Path(image_path).suffix.lower()))
                except OSError:
                    pass

            mask_png = sample_dir / "predicted_mask.png"
            prob_npy = sample_dir / "predicted_mask_prob.npy"
            overlay_png = sample_dir / "overlay.png"
            np.save(prob_npy, prob.astype(np.float32))
            imwrite_or_raise(mask_png, (binary.astype(np.uint8) * 255))
            overlay = img_rgb.copy().astype(np.float32)
            overlay[binary] = overlay[binary] * 0.55 + np.array([255, 0, 0], np.float32) * 0.45
            imwrite_or_raise(overlay_png, cv2.cvtColor(np.clip(overlay, 0, 255).astype(np.uint8),
                                                       cv2.COLOR_RGB2BGR))
            (sample_dir / "text.txt").write_text(text_output + "\n", encoding="utf-8")

            pos_frac = float(binary.mean())
            # LISA has no classification head — derive a document-level decision.
            derived_label = "tampered" if pos_frac > 0 else "real"
            result = {
                "sample_index": index,
                "image_path": image_path,
                "text": text_output,
                "cls_head": {
                    "predicted_label": derived_label,
                    "probabilities": {"real": 1.0 - min(pos_frac * 5, 1.0),
                                      "tampered": min(pos_frac * 5, 1.0)},
                    "source": "derived_from_mask (LISA has no [CLS] head)",
                },
                "obj_head": None,   # LISA has no [OBJ] head
                "localization": {
                    "mask_threshold": args.mask_threshold,
                    "mask_png": str(mask_png),
                    "mask_prob_npy": str(prob_npy),
                    "overlay_png": str(overlay_png),
                    "shape": list(prob.shape),
                    "positive_pixel_fraction": pos_frac,
                },
            }
            (sample_dir / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            errors.append({"sample_index": index, "image_path": image_path, "error": str(exc)})
            print(f"  ERROR: {exc}", file=sys.stderr, flush=True)

    (output_dir / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "sample_index", "image_path", "predicted_label",
            "positive_pixel_fraction", "overlay_png", "mask_png"])
        w.writeheader()
        for r in results:
            w.writerow({
                "sample_index": r["sample_index"],
                "image_path": r["image_path"],
                "predicted_label": r["cls_head"]["predicted_label"],
                "positive_pixel_fraction": r["localization"]["positive_pixel_fraction"],
                "overlay_png": r["localization"]["overlay_png"],
                "mask_png": r["localization"]["mask_png"],
            })
    if errors:
        (output_dir / "errors.json").write_text(
            json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nSaved {len(results)} LISA result(s) to {output_dir}")
    if errors:
        print(f"{len(errors)} image(s) failed; see {output_dir / 'errors.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
