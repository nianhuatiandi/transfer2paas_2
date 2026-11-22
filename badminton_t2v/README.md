# Badminton text-to-video comparison

The reference is the [eight-second badminton practice clip](../badminton_lift_31679122798_first8s.mp4). The experiment crosses two video generators, four caption sources, and three prompt variants for 24 generations.

- **Original** uses each captioner's raw output.
- [Plain language](prompts/plain.txt) specifies two diagonal approaches, an upward return toward the left and then the right side of the far court, and a return to the starting position after each shot.
- [Technical terms](prompts/technical.txt) describes the same sequence using badminton terms such as *chassé steps* and *lift*.

All generations use seed 42, 1344×768 output at 24 fps, and each model's native audio generation. Both pipelines take text only.

| Model | Checkpoint and inference | Frames |
| --- | --- | ---: |
| MiniMax H3 Base | Public FL2VA checkpoint in text-to-audio-video mode, BF16, FlashAttention 3, 50 scheduler points, 49 denoiser evaluations | 192 |
| LTX 2.3 | 22B dev, 30-step first stage, distilled LoRA 384 1.1 and spatial upscaler ×2 1.1 for the second stage | 193 |

MiniMax H3 weights are from Hugging Face revision `1cc7549f2cf0af8ff2f09b24f3c57303c8aa6317`, with Diffusers revision `f53d552036a0d1bd5570782a39cd40cfabf112bc`. LTX 2.3 uses Lightricks' source at revision `d6053703e00195bc668cbd1d5eda9dc0b2e7b74a`.

The three AVowed texts take 1,559 to 1,602 Gemma tokens. Their LTX runs use a 1,664-token text encoder limit so the whole caption fits. Other LTX runs use the default 1,024 tokens. TimeChat prompts retain the JSON and timestamps from the source caption, which includes a segment at 00:10–00:12. The generated TimeChat videos use the same approximately eight-second duration as the other groups.

The evaluation uses a single video and one seed per model. Check the generated video for the two approaches, the type and order of the two strokes, the visible shuttle trajectory, and a recovery after each stroke.

## Outputs

| Caption source | Prompts | MiniMax H3 clips | MiniMax H3 comparison | LTX 2.3 clips | LTX 2.3 comparison |
| --- | --- | --- | --- | --- | --- |
| AVowed | [Original](prompts/avowed/original.txt) · [Plain](prompts/avowed/plain.txt) · [Technical](prompts/avowed/technical.txt) | [Original](minimax_h3/avowed/original.mp4) · [Plain](minimax_h3/avowed/plain.mp4) · [Technical](minimax_h3/avowed/technical.mp4) | [Compare](minimax_h3/avowed/comparison.mp4) | [Original](ltx23/avowed/original.mp4) · [Plain](ltx23/avowed/plain.mp4) · [Technical](ltx23/avowed/technical.mp4) | [Compare](ltx23/avowed/comparison.mp4) |
| AVoCaDO | [Original](prompts/avocado/original.txt) · [Plain](prompts/avocado/plain.txt) · [Technical](prompts/avocado/technical.txt) | [Original](minimax_h3/avocado/original.mp4) · [Plain](minimax_h3/avocado/plain.mp4) · [Technical](minimax_h3/avocado/technical.mp4) | [Compare](minimax_h3/avocado/comparison.mp4) | [Original](ltx23/avocado/original.mp4) · [Plain](ltx23/avocado/plain.mp4) · [Technical](ltx23/avocado/technical.mp4) | [Compare](ltx23/avocado/comparison.mp4) |
| DiaDem | [Original](prompts/original.txt) · [Plain](prompts/plain.txt) · [Technical](prompts/technical.txt) | [Original](minimax_h3/original.mp4) · [Plain](minimax_h3/plain.mp4) · [Technical](minimax_h3/technical.mp4) | [Compare](minimax_h3/comparison.mp4) | [Original](ltx23/original.mp4) · [Plain](ltx23/plain.mp4) · [Technical](ltx23/technical.mp4) | [Compare](ltx23/comparison.mp4) |
| TimeChat | [Original](prompts/timechat/original.txt) · [Plain](prompts/timechat/plain.txt) · [Technical](prompts/timechat/technical.txt) | [Original](minimax_h3/timechat/original.mp4) · [Plain](minimax_h3/timechat/plain.mp4) · [Technical](minimax_h3/timechat/technical.mp4) | [Compare](minimax_h3/timechat/comparison.mp4) | [Original](ltx23/timechat/original.mp4) · [Plain](ltx23/timechat/plain.mp4) · [Technical](ltx23/timechat/technical.mp4) | [Compare](ltx23/timechat/comparison.mp4) |

The comparison videos place the original, plain-language, and technical prompts from left to right. The individual clips contain the generated audio.

## DiaDem pilot observations

In the MiniMax H3 pair, the near player moves right and recovers at similar points in both clips, around 1.5–2.5 s and 5.5–6.5 s. The shuttle is difficult to follow, so the prescribed left-then-right trajectories are unverified. The LTX 2.3 pair contains visible high racket swings, including an overhead swing in the first 1.5 s of the technical clip. The intended two lifts with recovery after each are unclear in both clips.

## Observations from the additional captions

- **AVowed:** MiniMax H3's plain and technical videos show similar rightward movement and recovery. Both generators reproduce the black shirt with a pink back motif and the closer shot of the speaker near the end.
- **AVoCaDO:** MiniMax H3's original video shows a jumping overhead swing around 2 s. In the technical video, the near player's rightward movement and intermediate recovery are clearer early in the clip. The shuttle's two intended trajectories are difficult to verify.
- **TimeChat:** The plain-language and technical videos from both generators still show high or overhead swings. The left-then-right lift sequence is unclear.

Across the four caption sources, this single-seed run shows no consistent advantage for the technical wording over the plain-language wording.
