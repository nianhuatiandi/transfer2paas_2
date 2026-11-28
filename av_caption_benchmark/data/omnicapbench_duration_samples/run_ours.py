"""Run the existing English benchmark on pinned OmniCapBench source videos."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import av

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "transfer2paas_2_git"
sys.path.insert(0, str(REPO))
from sports_annotation import bench
from sports_annotation.bench_reference import shot_scopes
from sports_annotation.io_utils import file_hash, write_json
from sports_annotation.long_video import media, run_lock, windows
from sports_annotation.media import ffmpeg_path, run_ffmpeg


def prepare(src, out):
    out.mkdir(parents=True, exist_ok=True)
    with run_lock(out):
        with av.open(str(src)) as source:
            duration = source.duration / av.time_base
            has_audio = bool(source.streams.audio)
        wav = out / "full.wav" if has_audio else None
        if wav and not wav.exists():
            partial = out / "full.part.wav"
            run_ffmpeg(
                ffmpeg_path(), "-v", "error", "-copyts", "-start_at_zero", "-i", src,
                "-map", "0:a:0", "-vn", "-af", "aresample=16000:async=1:first_pts=0",
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", partial,
            )
            partial.replace(wav)
        prepared_windows = list(windows(duration, 15, 3))
        for window in prepared_windows:
            media(out/f"w{window['n']:05}"/"media", src, wav, *window["span"])
        scopes = shot_scopes(src, duration)
        write_json(out/"preflight.json", {
            "source_sha256": file_hash(src),
            "duration_s": duration,
            "has_audio": has_audio,
            "windows": prepared_windows,
            "provisional_visual_review_scopes": scopes,
            "initial_model_calls": 1+len(prepared_windows)*(3 if has_audio else 2),
            "scope_model_calls": 2*len(scopes),
        })
        print(src.stem, len(prepared_windows), "windows,", len(scopes), "review scopes", flush=True)


def load_windows_credential():
    if os.getenv("QWEN_API_KEY"):
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            key, _ = winreg.QueryValueEx(env, "QWEN_API_KEY")
    except FileNotFoundError:
        return
    if isinstance(key, str) and key.strip():
        os.environ["QWEN_API_KEY"] = key.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Omit to process the nine official clips.")
    parser.add_argument("--prepare", action="store_true", help="Make local media windows only.")
    parser.add_argument("--draft", action="store_true", help="Run live model through draft only.")
    parser.add_argument("--prompt-key", action="store_true", help="Read the credential without echo from the terminal.")
    parser.add_argument("--english-asr", action="store_true", help="Use local English ASR when applicable.")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    entries = json.loads((HERE/"manifest.json").read_text(encoding="utf8"))
    rows = {row["id"]: row for row in entries}
    ids = args.ids or list(rows)
    if set(ids)-rows.keys():
        parser.error("Unknown video ID")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if not args.prepare:
        load_windows_credential()
        if not os.getenv("QWEN_API_KEY") and args.prompt_key:
            key = getpass.getpass("Qwen credential: ").strip()
            if key:
                os.environ["QWEN_API_KEY"] = key
        if not os.getenv("QWEN_API_KEY"):
            raise SystemExit("Live annotation requires QWEN_API_KEY. Offline preparation does not.")
    asr_root = Path(tempfile.gettempdir())/"av_threepass_asr_20261127"
    model = asr_root/"vosk-model-small-en-us-0.15"
    if args.english_asr:
        sys.path.insert(0,str(asr_root/"deps"))

    def process(k):
        src = HERE/rows[k]["file"]
        out = src.parent/"ours"
        if args.prepare:
            prepare(src, out)
            return
        # Use the general-purpose prompt with no labels or time hints from official GT.
        asr_model = model if args.english_asr and k!="000134" and model.is_dir() else None
        bench.run(SimpleNamespace(video=src, out=out, lexicon=None, vosk_model=asr_model,
                                  jobs=3, proposal_only=args.draft))
        print(k, "draft ready" if args.draft else "annotations and silver reference ready", flush=True)

    failures = []
    with ThreadPoolExecutor(args.workers) as pool:
        completed = {pool.submit(process, k): k for k in ids}
        for future in as_completed(completed):
            try:
                future.result()
            except Exception as exc:
                failures.append(completed[future])
                print("Stopped", completed[future], str(exc)[:500], flush=True)
    if failures:
        raise SystemExit(f"Failed cases: {', '.join(failures)}")


if __name__ == "__main__":
    main()
