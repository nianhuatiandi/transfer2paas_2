# Badminton text-to-video comparison

The reference is the [eight-second badminton practice clip](../badminton_lift_31679122798_first8s.mp4). Each model received one of three English text prompts.

- [Original](prompts/original.txt) uses the DiaDem caption, which describes the near player's returns as lunges and jumps.
- [Plain language](prompts/plain.txt) specifies two diagonal approaches, an upward return toward the left and then the right side of the far court, and a return to the starting position after each shot.
- [Technical terms](prompts/technical.txt) describes the same sequence using badminton terms such as *chassé steps* and *lift*.

The six generations use seed 42, 1344×768 output at 24 fps, and each model's native audio generation. Both pipelines take text only.

| Model | Checkpoint and inference | Frames |
| --- | --- | ---: |
| MiniMax H3 Base | Public FL2VA checkpoint in text-to-audio-video mode, BF16, FlashAttention 3, 50 scheduler points, 49 denoiser evaluations | 192 |
| LTX 2.3 | 22B dev, 30-step first stage, distilled LoRA 384 1.1 and spatial upscaler ×2 1.1 for the second stage | 193 |

MiniMax H3 weights are from Hugging Face revision `1cc7549f2cf0af8ff2f09b24f3c57303c8aa6317`, with Diffusers revision `f53d552036a0d1bd5570782a39cd40cfabf112bc`. LTX 2.3 uses Lightricks' source at revision `d6053703e00195bc668cbd1d5eda9dc0b2e7b74a`.

The evaluation uses a single video and one seed per model. Check the generated video for the two approaches, the type and order of the two strokes, the visible shuttle trajectory, and a recovery after each stroke.

## Outputs

| Model | Original | Plain language | Technical terms | Synchronized comparison |
| --- | --- | --- | --- | --- |
| MiniMax H3 | [Video](minimax_h3/original.mp4) | [Video](minimax_h3/plain.mp4) | [Video](minimax_h3/technical.mp4) | [Video](minimax_h3/comparison.mp4) |
| LTX 2.3 | [Video](ltx23/original.mp4) | [Video](ltx23/plain.mp4) | [Video](ltx23/technical.mp4) | [Video](ltx23/comparison.mp4) |

The comparison videos place the original, plain-language, and technical prompts from left to right. The individual clips contain the generated audio.

In the MiniMax H3 pair, the near player moves right and recovers at similar points in both clips, around 1.5–2.5 s and 5.5–6.5 s. The shuttle is difficult to follow, so the prescribed left-then-right trajectories are unverified. The LTX 2.3 pair contains visible high racket swings, including an overhead swing in the first 1.5 s of the technical clip. The intended two lifts with recovery after each are unclear in both clips. This pilot shows no clear improvement from the technical wording.
