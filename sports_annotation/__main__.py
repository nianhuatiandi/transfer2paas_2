import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from .pipeline import PACKAGE, assemble, bind_run, load_config, prepare_case, review_case, run_candidates
from .io_utils import write_json


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv[:1]==["bench"]:
        from .bench import main as run_bench
        return run_bench(argv[1:])
    if argv[:1]==["bench-adjudicate"]:
        from .bench_adjudicate import main as adjudicate
        return adjudicate(argv[1:])
    if argv[:1]==["long"]:
        from .long_video import main as run_long
        return run_long(argv[1:])
    parser = argparse.ArgumentParser(description="Sports candidate annotation. For windowed inputs use: python -m sports_annotation long --help.")
    parser.add_argument("command", choices=["prepare", "run", "review", "assemble", "validate"])
    parser.add_argument("--config", type=Path, default=PACKAGE / "config/five_videos.json")
    parser.add_argument("--run-dir", type=Path, default=PACKAGE / "runs/pilot_v01")
    parser.add_argument("--case", action="append", help="Case ID; repeat to select several. Default: all.")
    parser.add_argument("--with-review", action="store_true", help="run: include a separate evidence review API stage")
    parser.add_argument("--dry-run", action="store_true", help="prepare request records without sending them")
    args = parser.parse_args(argv)
    config, root = load_config(args.config)
    cases = [c for c in config["cases"] if not args.case or c["id"] in args.case]
    if args.case and set(args.case) - {c["id"] for c in cases}:
        parser.error("Unknown --case ID")
    protocol = bind_run(args.run_dir, config)
    key_cache = []

    def key():
        if not key_cache:
            value = os.environ.get(config["provider"].get("api_key_env", "QWEN_API_KEY"))
            key_cache.append(value if value else getpass.getpass("Qwen API key (hidden, not saved): "))
        return key_cache[0]

    reports = []
    for case in cases:
        out, manifest, lexicon, locked, external_hash, prepared = prepare_case(config, root, case, args.run_dir, protocol)
        print(json.dumps(prepared, ensure_ascii=False), flush=True)
        if args.command == "prepare" or (args.command == "run" and args.dry_run):
            reports.append(prepared)
            continue
        if args.command == "run":
            run_candidates(config, out, manifest, lexicon, locked, external_hash, protocol, key)
        if args.command == "review" or (args.command == "run" and args.with_review):
            plan = review_case(config, out, manifest, lexicon, locked, external_hash, protocol, key, args.dry_run)
            if args.dry_run:
                reports.append({"id": case["id"], "review_request_prepared": True, "review_frames": plan["review_frames"], "api_calls": 0})
                continue
        reports.append({"id": case["id"], **assemble(out, manifest, lexicon, locked, external_hash)})
    write_json(args.run_dir / ("prepare_summary.json" if args.command == "prepare" else f"{args.command}_summary.json"), reports)
    print("Run directory:", args.run_dir.resolve(), flush=True)


if __name__ == "__main__":
    main()
