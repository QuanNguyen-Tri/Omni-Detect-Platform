# Handoff — Image-Tampering Detection Baselines: Model Input / Output Spec

> Audience: platform / serving engineers.
> Goal: before wiring PIXAR / SIDA / LISA into the platform, know exactly **what each model consumes and produces**.

---

## 0. Orientation (read this first — avoids the #1 misconception)

These models do **image / pixel-level tampering detection & localization** — **not text detection**.
- **Input**: one **image** (+ a fixed instruction prompt, already built in; the platform usually doesn't touch it).
- **Output**: for that image — an **image-level label + which object was tampered + a pixel-level mask + a natural-language description** (each model supports a different subset; see §3).

All three are VLM + SAM architectures (LLaVA/LLaMA + CLIP ViT-L/14 + SAM ViT-H), each in 7B / 13B sizes → 6 checkpoints total.

---

## 1. Capability matrix (input → output)

| model | **input: image** | **binary-classification** | **object-level** | **pixel-level** | **text** |
|---|:---:|:---:|:---:|:---:|:---:|
| PIXAR-7B  | ✓ | ✓ | ✓ | ✓ | ✓ |
| PIXAR-13B | ✓ | ✓ | ✓ | ✓ | ✓ |
| SIDA-7B   | ✓ | ✓ | **N**¹ | ✓ | ✓ |
| SIDA-13B  | ✓ | ✓ | **N**¹ | ✓ | ✓ |
| LISA-7B   | ✓² | **N**³ | **N** | ✓ | ✓ |
| LISA-13B  | ✓² | **N**³ | **N** | ✓ | ✓ |

Legend: **✓** = natively supported & meaningful · **N** = not supported / not meaningful.

1. **SIDA has no `[OBJ]` head** (its tokenizer lacks the `[OBJ]` token) → the object output is random noise and is **suppressed** by the toolkit.
2. **LISA is instruction-driven**: it needs the image **and** a text instruction (the segmentation prompt).
3. **LISA has no classification head**; a document-level label is only **derived** from whether the predicted mask is non-empty (not a real classifier). LISA is a weak zero-shot baseline and often returns a near-empty mask for tampering.

---

## 2. Input (uniform across all models)

| Item | Description |
|---|---|
| **Primary input** | 1 RGB image (PNG/JPG/…, any resolution). **Not text.** |
| **Instruction prompt** | Built in. PIXAR/SIDA: "Can you identify whether this image is real, fully synthetic, or tampered? …". LISA: "Please segment the manipulated or tampered region in this image.". The platform normally doesn't need to pass it. |
| **Batch** | A set of images: folder / `.txt` / `.json` / `.jsonl` / `.csv` (see §4). |

For serving, each image is preprocessed into two tensors fed to the model (see §5):
- **CLIP tensor** `[1,3,224,224]` (`openai/clip-vit-large-patch14` preprocessing)
- **SAM tensor** `[1,3,1024,1024]` (ResizeLongestSide → pad)

---

## 3. Output (four granularities)

One forward pass over one image produces up to 4 things:

| Granularity | Meaning | Source head | Shape / type | Result field (JSON) |
|---|---|---|---|---|
| **document (image-level)** | whole-image `real` / `tampered` + probabilities | `[CLS]` | 3-way softmax (real / fully-synthetic / tampered); collapsed to binary on the platform side | `cls_head.predicted_label`, `cls_head.probabilities` |
| **object-level** | which object categories were tampered, top-k | `[OBJ]` | 81 classes (80 COCO + background), sigmoid | `obj_head.top_k[]` |
| **pixel-level** | tampering **mask** | `[SEG]`→SAM | `[H0,W0]` mask (original resolution), binary + probability map | `localization.mask_png / mask_prob_npy / overlay_png / positive_pixel_fraction` |
| **text** | natural-language description of "what was edited" | LM generation | string | `text` |

> ⚠️ **No bounding boxes.** Localization is always a **per-pixel mask**, never a box. The mask is at **original image resolution**.

---

## 4. Integration path A: the toolkit CLI (recommended, least effort)

Single entry point `baselines/run.py` (or the `run_baselines.sh` wrapper). The platform only supplies the **input** and the **model list**.

**Input** `--input` accepts: a single image / a folder (recursively globbed for `.png/.jpg/.jpeg/.bmp/.webp/.tif`) / `.txt` (one path per line) / `.json` (`[...]` or `{"images":[...]}`) / `.jsonl` (one `{"image_path":...}` per line) / `.csv` (image column auto-detected among `image_path/path/file…`).

```bash
# single image, all three default models
python baselines/run.py --input img.png --output_dir out --gpu 0 --precision bf16
# a batch (folder), pick models
python baselines/run.py --input images/ --models PIXAR-7B SIDA-7B LISA-7B \
    --output_dir out --gpu 0 --precision bf16
```

**Output directory layout:**
```
out/
├── _inputs.jsonl              # normalized image list (shared by every model)
├── summary_all.json           # cross-model summary: each record = one (model, image), all granularities
├── summary_all.csv            # one row per (model, image)
└── <MODEL>/
    ├── summary.json / summary.csv
    └── sample_0001_<name>_<hash>/
        ├── cls_head.json          # document level
        ├── obj_head.json          # object level (meaningful only for PIXAR)
        ├── predicted_mask.png     # pixel level, binary mask
        ├── predicted_mask_prob.npy# probability map [H,W] float32
        ├── overlay.png            # red highlight on the original image
        ├── text.txt               # description
        └── result.json            # all of the above combined
```

**Core JSON the platform parses (`summary_all.json` → each `results[]` record):**
```json
{
  "model": "PIXAR-7B",
  "image_path": "/abs/edited_042.png",
  "document_level": { "label": "tampered", "p_real": 0.05, "p_tampered": 0.95, "source": "[CLS] head" },
  "object_level":   [ { "name": "dog", "prob": 0.87 } ],        // null for SIDA/LISA
  "object_level_note": null,                                     // SIDA carries a "suppressed" note
  "pixel_level":    { "mask_png": "...", "overlay_png": "...", "positive_pixel_fraction": 0.045 },
  "text": "The image is tampered. The bus was replaced ..."
}
```

The per-model `<MODEL>/result.json` (written by `inference.py`) has finer `cls_head` / `obj_head` / `localization` fields — read it if the platform needs raw probabilities.

---

## 5. Integration path B: calling the models directly (for custom serving)

If the platform bypasses the CLI and keeps models resident, the interfaces are:

**PIXAR / SIDA** (`model/PIXAR.py::PIXARForCausalLM.evaluate`):
```python
output_ids, pred_masks, obj_preds, cls_info = model.evaluate(
    images_clip,          # [1,3,224,224]  CLIP-preprocessed
    images,               # [1,3,1024,1024] SAM-preprocessed
    input_ids,            # [1,T] prompt (contains <image> and the assistant-side "[CLS] [OBJ] [SEG]")
    resize_list,          # [(h,w)] size after SAM resize
    original_size_list,   # [(H0,W0)] original image size
    max_new_tokens=64, tokenizer=tokenizer,
    cls_label=2,          # forces the seg/obj branch to run; the real class is in cls_info
    generate_text=True,
)
# returns:
#   cls_info   = {"predicted_class":0/1/2, "label", "probabilities":{real, fully synthetic, tampered}}
#   pred_masks = [ Tensor[H0,W0] ]  tampering-mask logits (original resolution; [] on non-tampered early exit)
#   obj_preds  = Tensor[81] sigmoid (meaningless for SIDA)
#   output_ids = generated text tokens
```

**LISA** (`lisa/model/LISA.py::LISAForCausalLM.evaluate`):
```python
output_ids, pred_masks = model.evaluate(
    image_clip, image, input_ids, [resize], [(H0,W0)],
    max_new_tokens=64, tokenizer=tokenizer,
)
# returns: pred_masks[0] = Tensor[n,H0,W0] logits; empty when no [SEG] was generated → treat as empty mask
# LISA has no cls/obj. Mask binarization: logit>0 (equivalent to prob>0.5).
```

Reference implementations: PIXAR/SIDA → `pixel-tampering-dg/inference.py`; LISA → `baselines/infer_lisa.py` (both are single-image loops; copy the pre/post-processing directly).

---

## 6. Resource & precision requirements (important)

| Model | Params | **bf16 VRAM (single GPU)** | Dependencies |
|---|---|---|---|
| *-7B  | 7B  | **~16–17 GB** | + SAM ViT-H (~2.5 GB) + CLIP (auto) |
| *-13B | 13B | **~28 GB**    | same |

- **Must use `--precision bf16` (or fp32).** Measured: **4-bit quantization corrupts the SAM mask decoder** — it collapsed SIDA's mask from 26.5% to 0% and produced NaN for LISA. fp16 is also numerically risky for SAM. **In production, always use bf16.**
- PIXAR / SIDA need the external **SAM ViT-H** weights (`--vision_pretrained sam_vit_h_4b8939.pth`); **LISA has SAM merged into its checkpoint** — no external SAM needed.
- **CLIP ViT-L/14** (`openai/clip-vit-large-patch14`) is auto-downloaded from HF at load time (needs HF access or a pre-populated cache).
- Weights (HF): PIXAR `jiachengcui888/PIXAR-{7B,13B}`, SIDA `saberzl/SIDA-{7B,13B}`, LISA `xinlai/LISA-7B-v1` and `xinlai/LISA-13B-llama2-v1`. See `baselines/setup.sh`.

---

## 7. Caveats / gotchas

1. **SIDA's `obj_head` is meaningless** (no `[OBJ]` token, random weights) → suppressed by the toolkit. If wiring SIDA directly, ignore its obj output.
2. **LISA is segmentation-only**: no classification / object head; its document label is derived from the mask and is **only meaningful on tampered images** (LISA does not judge real/fake).
3. `inference.py` internally passes `cls_label=2`, which **forces the seg branch to run** (so a mask is produced even when CLS predicts real). **The real image-level decision must be read from `cls_head.predicted_label`** — do not infer it from "was a mask produced".
4. Localization is a **pixel mask, not a box**; the mask is at **original resolution**.
5. **No online / API baselines** (no ChatGPT/Claude/Gemini calls) — everything is a local, offline model.
6. Normalizing `.csv` / folder / `.jsonl` inputs is handled by `baselines/prepare_inputs.py`; the platform can reuse it to turn arbitrary inputs into an image-path list.

---

## 8. Validation status (as of handoff)

- ✅ **Pipeline validated end-to-end on a real GPU**: single-image and folder inputs → 6-model registry → all granularities → aggregation, all working.
- ✅ **Faithful 7B bf16 results** (sample `tampered_0a43da0cc96bd5ee.png`): PIXAR-7B `tampered(0.95)` + 13% mask + "the bus was replaced"; SIDA-7B mask 26.5%; LISA-7B near-empty mask (weak zero-shot).
- ⏳ **13B bf16 pending**: needs a GPU with ~28 GB free. Command (no shim required):
  ```bash
  python baselines/run.py --input <image/folder> --output_dir <out> \
      --gpu <id> --precision bf16 --models PIXAR-13B SIDA-13B LISA-13B
  ```
- ℹ️ 4-bit + a temporary shim was used only to stack on fully-loaded cards for an internal smoke test. **Do not use it in production** (it corrupts masks; see §6).

---

**Related files**: `baselines/README.md` (toolkit overview), `baselines/run.py` (entry point), `baselines/prepare_inputs.py` (input normalization), `baselines/infer_lisa.py` (LISA inference), `pixel-tampering-dg/inference.py` (PIXAR/SIDA inference).
