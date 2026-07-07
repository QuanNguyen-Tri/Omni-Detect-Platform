# `baselines/` — one-click PIXAR / SIDA / LISA tampering-detection runner

> **Task note.** This repo detects **image / pixel-level tampering**, not text.
> The three baselines are image VLM + SAM segmentation models. The "document /
> sentence-paragraph / word" granularities map onto the image task as:
>
> | requested level | here it means | head |
> |---|---|---|
> | **document-level** | whole-image `real` vs `tampered` | `[CLS]` |
> | **sentence/paragraph-level** | which object was tampered (+ free-text edit description) | `[OBJ]` + LM text |
> | **word-level** | dense **pixel** tampering mask (finer than a word) | `[SEG]` → SAM |
>
> There is no bounding-box output and no per-token text metric anywhere in the repo.

## What this gives you

One entry point that runs **single** or **batch** inference across the offline
baselines and prints all granularities side by side:

| model | loader | document `[CLS]` | object `[OBJ]` | pixel `[SEG]` | text |
|---|---|:---:|:---:|:---:|:---:|
| PIXAR-7B / PIXAR-13B | `inference.py` (`PIXARForCausalLM`) | ✅ | ✅ | ✅ | ✅ |
| SIDA-7B / SIDA-13B | `inference.py` (same class) | ✅ | n/a | ✅ | ✅ |
| LISA-7B / LISA-13B | `infer_lisa.py` (`LISAForCausalLM`) | ➖ derived¹ | ➖ n/a | ✅ | ✅ |

¹ LISA has no classification head; the document-level label is **derived** from whether the predicted mask is non-empty.

Online API baselines (ChatGPT / Claude / Gemini as judges) **do not exist** in this repo and are intentionally out of scope here (offline local models only).

## Files

| file | role |
|---|---|
| `setup.sh` | download weights + tokenizer/config (HF snapshots) for the 6 models + SAM ViT-H. Idempotent. Skips the ~260 GB datasets. |
| `run.py` | **main entry** — normalize input → run each model → combined, granularity-labelled summary. |
| `run_baselines.sh` | thin one-click wrapper (`--setup` + forwards to `run.py`). |
| `prepare_inputs.py` | normalize *image / folder / .txt / .json / .jsonl / .csv* → a flat list of image paths (the folder-scan + CSV support `inference.py` lacks). |
| `infer_lisa.py` | LISA loose-image inference worker (mirrors `lisa/eval_lisa.py`'s load path; no GT masks needed). |

## Quickstart

```bash
# 0) (once) download weights — idempotent; skips anything already present.
bash baselines/setup.sh                         # all 6 + SAM
bash baselines/setup.sh --check                 # just report present/missing
bash baselines/setup.sh --models "PIXAR-7B SIDA-7B LISA-7B"

# 1) SINGLE-request inference on one image (all 3 default baselines)
bash baselines/run_baselines.sh --input path/to/image.png --output_dir out --gpu 0

# 2) BATCH over a folder of images
bash baselines/run_baselines.sh --input path/to/images_dir/ --output_dir out --gpu 0

# 3) BATCH from a list file (CSV / JSONL / JSON / TXT)
bash baselines/run_baselines.sh --input batch.csv   --output_dir out --gpu 0
bash baselines/run_baselines.sh --input batch.jsonl --output_dir out --gpu 0

# choose a subset of models; cap images for a smoke test
bash baselines/run_baselines.sh --input images/ --models PIXAR-7B LISA-7B \
    --output_dir out --gpu 0 --limit 8

# see the exact per-model commands WITHOUT running (no GPU needed)
python baselines/run.py --input images/ --output_dir out --dry-run
```

**Batch input formats** (`--input`): a directory (recursively globbed for
`.png/.jpg/.jpeg/.bmp/.webp/.tif`), or a `.txt` (one path per line, `#` comments),
`.json` (`[...]` or `{"images":[...]}`), `.jsonl` (one `{"image_path":...}` or bare
string per line), or `.csv` (image column auto-detected among `image_path/path/file/…`,
else first column).

## Outputs

```
out/
├── _inputs.jsonl              # the normalized image list shared by every model
├── summary_all.json           # combined, granularity-labelled records + per-model status
├── summary_all.csv            # one row per (model, image): doc label, p_tampered, top object, pos-pixel%
├── PIXAR-7B/
│   ├── summary.json  summary.csv
│   └── sample_0001_<name>_<hash>/
│       ├── input.png  source.<ext>
│       ├── cls_head.json        # document-level: real vs tampered (+ 3-way raw)
│       ├── obj_head.json        # object-level: top-k tampered COCO categories  (PIXAR only)
│       ├── predicted_mask.png   # word/pixel-level: binary tampering mask
│       ├── predicted_mask_prob.npy   overlay.png
│       ├── text.txt             # free-text edit description
│       └── result.json
├── SIDA-7B/ …                  # same layout; obj_head present but not meaningful
└── LISA-7B/ …                  # mask + text + derived cls; no obj_head
```

The console prints a table like:

```
model      doc        p_tamp top_object     pos_pix%  image
PIXAR-7B   tampered     0.912 dog               4.53  edited_042.png
SIDA-7B    tampered     0.774 -                 3.98  edited_042.png
LISA-7B    tampered     0.800 -                 3.11  edited_042.png
```

## Environment / paths

* Weights live under `pretrains/` (a symlink to `/data/tan1/pretrains`): `PIXAR-7B`, `PIXAR-13B`,
  `SIDA-7B`, `SIDA-13B`, `LISA-7B`, `LISA-13B`, `sam_vit_h_4b8939.pth`. CLIP ViT-L/14 auto-downloads at load.
* Runner defaults to the `pixar` conda env at `/home/omnidet/miniconda3/envs/pixar/bin/python`
  (override with `--python` or `PYTHON=...`). PIXAR/SIDA additionally need SAM ViT-H (`--vision_pretrained`);
  LISA has SAM merged into its checkpoint.
* `--gpu N` selects one GPU per run (both workers are single-GPU sequential, like `inference.py`).
  For large labelled-dataset **metric** evaluation (gIoU/cIoU/F1, per-generator), use the repo's
  multi-GPU `pixel-tampering-dg/test_parallel.py` / `lisa/eval_lisa.py` instead — this toolkit is for
  running detection and showing per-image outputs, not benchmark scoring.

