Badminton annotation pipeline v0.8

Run from E:\Download\sports_video_data:
    python .tools/run_badminton_pipeline.py

The key is entered through a hidden prompt. It is not written to files.

Prompt files:
- badminton_prompt.txt: shared visual evidence policy and terminology.
- badminton_pipeline/visual_prompt.txt: per-shot visual JSON task.
- badminton_pipeline/audio_prompt.txt: audio-only transcription JSON task.
- badminton_pipeline/review_prompt.txt: targeted evidence review and training-delivery corrections.
- badminton_pipeline/alignment_prompt.txt: audiovisual correspondence review.

Processing:
1. Read source metadata and find candidate scene cuts with FFmpeg (threshold 0.12).
2. Decode local source frames, then select approximately 10 frames/second plus each shot's first and last frame. Stage records contain actual frame timestamps. This avoids relying on an API video's requested extraction rate.
3. Send each shot's timestamped frames to Qwen independently. Send the entire extracted 16-kHz mono WAV to a separate audio request.
4. Validate JSON, actor references, labels and shot-relative bounds. Sort events globally before assigning action IDs.
5. For each shot, review the original video WITH its audio, timestamped images, and candidate observations. Assess visible speaker identity, speech/action relations, and every action's sound association separately. Supported, uncertain, and none_detected are distinct model-review outcomes. Store independent audio and visual times and their offset. The final report includes these results. --skip-alignment stops after observations.

Outputs are under qwen3.8_omni_results/<time>_pipeline_<version>/:
- visual_S01.json, visual_S02.json, etc.: independent visual observations.
- audio.json: independent transcription and audible sounds.
- *_prompt.txt, *_metadata.json: exact stage prompts and usage records.
- media/manifest.json: source hash, cuts and actual selected frame times.
- badminton_response.txt: assembled four-section report.
- combined_annotations.json: merged data preserving model uncertainties.
- alignment.json and alignment_summary.json: reviewed links, timing, confidence, evidence and new API usage.
- av_alignment/: raw/validated per-shot alignment JSON, exact prompts and metadata.
- pipeline_validation.json and summary.json: checks and token usage.

Resume a failed run with the same prompts:
    python .tools/run_badminton_pipeline.py --resume qwen3.8_omni_results/<run_directory>
Completed stages are reused only when their prompt hash matches. Keep the same source file and prompts for a resume. For a new prompt revision, start a new run so comparisons stay isolated.

Re-render completed stages after improving local merging/validation, without using the API:
    python .tools/run_badminton_pipeline.py --resume qwen3.8_omni_results/<run_directory> --assemble-only

Refine the two sports shots of this three-shot clip while reusing its completed audio and closing shot:
    python .tools/refine_badminton_pipeline.py qwen3.8_omni_results/<baseline_pipeline_directory>
This writes a separate v0.7 comparison run, retains the candidate observations, and sends only S01 and S02 for review. It does not overwrite the baseline.

Add AV alignment to an existing result without rerunning visual analysis or transcription:
    python .tools/badminton_alignment.py --source-run qwen3.8_omni_results/<existing_pipeline_directory>
This writes a new v0.8 result directory and reuses the previous observations/media. To reuse completed alignment requests after a failure, add --resume qwen3.8_omni_results/<alignment_run_directory> with the same --source-run.
After all alignment responses are complete, add --cached-only to that resume command to revalidate/merge them without an API key or additional API calls. Cross-cut syllable duplication is flagged while preserving the original model fragments.

Alignment checks: valid actor/voice/action references, intervals within the reviewed shot, temporal overlap for overlap-only links, one assessment per action, and separate audio/visual timestamps. Low-confidence matches, missing anchor times, or offsets exceeding 0.200 s cannot be reported as supported. That tolerance is a review policy, not a measured synchronization accuracy. A changed source hash or action signature invalidates existing alignment. A potentially duplicated utterance fragment at a cut is flagged, not silently rewritten.

Limits: candidate cuts and model annotations need review on other clips. Local sampling establishes actual input-frame spacing, not exact event timing or ground-truth stroke labels. Supported AV links mean model-backed evidence, not human-verified lip synchronization or measured impact timing. Uncertain remains valid after review; none_detected means no distinct attributable sound was found, not that the video is silent. The visual stage may return fallback technique labels.
