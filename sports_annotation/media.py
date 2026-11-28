"""Decode presentation timestamps; do not infer time as frame_index / nominal_fps."""
import bisect
import hashlib
import io
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path

import av

from . import __version__
from .io_utils import file_hash, object_hash, read_json, write_json


def ffmpeg_path(setting=None):
    if setting and not Path(setting).is_file():
        raise FileNotFoundError("Configured FFmpeg binary does not exist: " + str(setting))
    candidates = [setting, shutil.which("ffmpeg"), "C:/Program Files (x86)/FormatFactory/ffmpeg.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise FileNotFoundError("FFmpeg not found; set media.ffmpeg in config")


def run_ffmpeg(binary, *args):
    proc = subprocess.run([binary, "-hide_banner", "-nostdin", *map(str, args)], capture_output=True, timeout=300)
    log = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode:
        raise RuntimeError("FFmpeg failed: " + log[-2000:])
    return log


def inspect_source(source):
    with av.open(str(source)) as container:
        if not container.streams.video:
            raise ValueError("No video stream")
        video = container.streams.video[0]
        starts = [float(s.start_time * s.time_base) for s in container.streams if s.start_time is not None]
        origin = container.start_time / av.time_base if container.start_time is not None else min(starts, default=0.0)
        audio = container.streams.audio[0] if container.streams.audio else None
        audio_info = {"present": audio is not None}
        if audio is not None:
            audio_start = float(audio.start_time * audio.time_base) - origin if audio.start_time is not None else 0.0
            audio_duration = float(audio.duration * audio.time_base) if audio.duration is not None else None
            audio_info.update({"source_start": audio_start, "source_duration": audio_duration,
                               "source_rate": audio.codec_context.sample_rate,
                               "source_channels": audio.codec_context.channels})
        rate = float(video.average_rate) if video.average_rate else None
        info = {"width": video.codec_context.width, "height": video.codec_context.height,
                "nominal_fps": rate, "timeline_origin_pts_seconds": origin, "audio": audio_info}
        rows = []
        for i, frame in enumerate(container.decode(video)):
            if frame.pts is None:
                raise ValueError("Missing frame PTS; timing requires explicit remediation")
            pts = float(frame.pts * frame.time_base)
            t = pts - origin
            if t < -1e-5 or (rows and t <= rows[-1]["time"]):
                raise ValueError("Non-monotonic/negative decoded presentation timestamps")
            duration = float(frame.duration * frame.time_base) if getattr(frame, "duration", 0) else None
            rows.append({"index": i, "pts_seconds": pts, "time": max(0.0, t), "duration": duration})
        if not rows:
            raise ValueError("No decoded video frames")
        fallback = (rows[-1]["time"] - rows[-2]["time"]) if len(rows) > 1 else 1 / (rate or 25)
        duration = rows[-1]["time"] + (rows[-1]["duration"] or fallback)
        for i, row in enumerate(rows):
            row["end"] = rows[i + 1]["time"] if i + 1 < len(rows) else duration
        info.update({"duration": duration, "frame_count": len(rows), "source_frames": rows,
                     "duration_basis": "last decoded video PTS plus frame exposure"})
        if audio is not None:
            # Stream.duration is often missing (e.g. Matroska). Decode timestamps
            # to distinguish real audio from the silence later added for alignment.
            audio_first, audio_last = None, None
            with av.open(str(source)) as audio_container:
                for frame in audio_container.decode(audio=0):
                    if frame.pts is None:
                        raise ValueError("Missing audio PTS")
                    onset = float(frame.pts * frame.time_base) - origin
                    audio_first = onset if audio_first is None else min(audio_first, onset)
                    offset = onset + frame.samples / frame.sample_rate
                    audio_last = offset if audio_last is None else max(audio_last, offset)
            if audio_first is None:
                raise ValueError("Audio stream exists but has no decodable samples")
            audio_info.update({"source_start": audio_first, "source_duration": audio_last - audio_first})
            start = max(0.0, audio_first)
            end = min(duration, audio_last)
            audio_info["valid_span"] = [start, max(start, end)]
        return info


def nearest_index(times, t):
    i = bisect.bisect_left(times, t)
    return min({max(0, i - 1), min(len(times) - 1, i)}, key=lambda n: (abs(times[n] - t), n))


def detect_shots(source, info, settings, binary, cuts=None):
    times = [f["time"] for f in info["source_frames"]]
    if cuts is None:
        threshold = settings.get("scene_threshold", 0.12)
        log = run_ffmpeg(binary, "-v", "info", "-copyts", "-i", source, "-an", "-vf",
                         f"select=gt(scene\\,{threshold}),showinfo", "-fps_mode", "vfr", "-f", "null", "-")
        cuts = [float(t) - info["timeline_origin_pts_seconds"] for t in re.findall(r"pts_time:([-0-9.e+]+)", log)]
        method = "ffmpeg_scene_candidates"
    else:
        method = "provided_cut_list"
        if not all(math.isfinite(t) and 0 <= t <= info["duration"] + 1e-5 for t in cuts):
            raise ValueError("Supplied cut lies outside this clip or is non-finite")
    # Snap cuts to real frame boundaries. Never coalesce logical shots by duration.
    cut_indices = sorted({nearest_index(times, t) for t in cuts if 0 < t < info["duration"]})
    cut_indices = [i for i in cut_indices if 0 < i < len(times)]
    boundaries = [0] + cut_indices + [len(times)]
    shots = []
    for i, (first, stop) in enumerate(zip(boundaries, boundaries[1:]), 1):
        shots.append({"id": f"S{i:02d}", "start": times[first] if first else 0.0,
                      "end": times[stop] if stop < len(times) else info["duration"],
                      "first_frame": first, "end_frame_exclusive": stop})
    return shots, {"method": method, "raw_candidates_seconds": cuts,
                   "status": "candidate_cuts_require_review", "logical_shots_preserved": True}


def sample_indices(info, shots, fps):
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("sampling_fps must be positive")
    times = [f["time"] for f in info["source_frames"]]
    selected = set()
    for shot in shots:
        first, stop = shot["first_frame"], shot["end_frame_exclusive"]
        selected.update((first, stop - 1))
        t = shot["start"]
        while t < shot["end"]:
            selected.add(min(stop - 1, max(first, nearest_index(times, t))))
            t += 1 / fps
    return sorted(selected)


def export_frames(source, info, indices, folder, max_width=None, quality=90):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    indices = set(indices)
    records = []
    with av.open(str(source)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if index not in indices:
                continue
            target = folder / f"frame_{index:06d}.jpg"
            image = frame.to_image()
            if max_width and image.width > max_width:
                image = image.resize((max_width, round(image.height * max_width / image.width)))
            encoded = io.BytesIO()
            image.save(encoded, format="JPEG", quality=quality)
            expected_hash = hashlib.sha256(encoded.getvalue()).hexdigest()
            if target.exists():
                if file_hash(target) != expected_hash:
                    raise ValueError("Existing frame differs from decoded source: " + str(target))
            else:
                target.write_bytes(encoded.getvalue())
            record = info["source_frames"][index]
            shot = next(s["id"] for s in info["shots"] if s["first_frame"] <= index < s["end_frame_exclusive"])
            records.append({"index": index, "time": record["time"], "end": record["end"], "shot_id": shot,
                            "file": f"frames/{target.name}", "sha256": file_hash(target),
                            "width": image.width, "height": image.height})
    if len(records) != len(indices):
        raise ValueError("Failed to export all selected frames")
    return records


def verify_prepared(media_dir, manifest):
    for frame in manifest["frames"]:
        if file_hash(media_dir / frame["file"]) != frame["sha256"]:
            raise ValueError("Prepared frame changed: " + frame["file"])
    if manifest["audio"]["present"]:
        if file_hash(media_dir / manifest["audio"]["file"]) != manifest["audio"]["sha256"]:
            raise ValueError("Prepared audio changed")


def prepare(source, media_dir, settings, cuts=None):
    source, media_dir = Path(source).resolve(), Path(media_dir)
    source_sha = file_hash(source)
    signature = object_hash({"source": source_sha, "source_path": str(source), "settings": settings,
                             "cuts": cuts, "version": __version__, "pyav": av.__version__})
    manifest_path = media_dir / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["preparation_signature"] != signature:
            raise ValueError("Preparation changed; use a new --run-dir")
        verify_prepared(media_dir, manifest)
        return manifest
    if media_dir.exists() and any(media_dir.iterdir()):
        raise ValueError("Incomplete preparation exists; use a new --run-dir")
    binary = ffmpeg_path(settings.get("ffmpeg"))
    info = inspect_source(source)
    if info["duration"] > settings.get("max_clip_seconds", 30):
        raise ValueError("Clip exceeds configured window limit; split explicitly and retain global offsets")
    info["shots"], cut_info = detect_shots(source, info, settings, binary, cuts)
    indices = sample_indices(info, info["shots"], settings.get("sampling_fps", 10))
    if len(indices) > settings.get("max_base_frames", 400):
        raise ValueError("Too many base frames; configure shorter windows or a lower sampling rate")
    media_dir.mkdir(parents=True, exist_ok=True)
    info["frames"] = export_frames(source, info, indices, media_dir / "frames",
                                    settings.get("max_frame_width"), settings.get("jpeg_quality", 90))
    if info["audio"]["present"]:
        output = media_dir / "audio.wav"
        duration, origin = info["duration"], info["timeline_origin_pts_seconds"]
        filters = f"asetpts=PTS-({origin})/TB,aresample=16000:async=1:first_pts=0,apad=whole_dur={duration},atrim=end={duration}"
        run_ffmpeg(binary, "-v", "error", "-copyts", "-i", source, "-map", "0:a:0", "-vn",
                   "-af", filters, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-n", output)
        with wave.open(str(output), "rb") as wav:
            wav_duration = wav.getnframes() / wav.getframerate()
        if abs(wav_duration - duration) > 0.002:
            raise ValueError("Normalized audio duration mismatch")
        info["audio"].update({"file": "audio.wav", "sha256": file_hash(output), "duration": wav_duration,
                              "normalization": "source PTS offset preserved; missing head/tail padded with silence"})
    info.update({"source": str(source), "source_sha256": source_sha, "preparation_signature": signature,
                 "cut_detection": cut_info, "requested_sampling_fps": settings.get("sampling_fps", 10),
                 "input_mode": "timestamped_local_images_not_api_video_fps", "settings": settings,
                 "tools": {"pyav": av.__version__, "ffmpeg": binary}})
    write_json(manifest_path, info)
    return info


def prepare_review(media_dir, manifest, visual, audio, settings, image_byte_budget=None):
    """All base frames plus native-rate local neighborhoods, under an explicit cap."""
    if file_hash(manifest["source"]) != manifest["source_sha256"]:
        raise ValueError("Source changed before review")
    priorities = []
    radius = settings.get("review_radius_seconds", 0.4)
    for action in visual["actions"]:
        for anchor in action["key_moments"]:
            if anchor["time"] is not None:
                priorities.append((0, anchor["time"], f"anchor:{action['id']}:{anchor['name']}"))
        for key in ("start", "end"):
            lo, hi = action[key + "_range"]
            uncertain = action["confidence"] != "high" or hi - lo > 0.1
            priorities.append((1 if uncertain else 2, action[key], f"boundary:{action['id']}:{key}"))
    for event in audio["events"]:
        for key in ("start", "end"):
            priorities.append((1, event[key], f"audio_boundary:{event['id']}:{key}"))
    if not visual["actions"]:
        priorities += [(0, s["start"] + (s["end"] - s["start"]) / 2, "empty_visual_inventory") for s in manifest["shots"]]
    chosen = {f["index"] for f in manifest["frames"]}
    base_indices = set(chosen)
    cap = max(len(chosen), settings.get("max_review_frames", 320))
    candidates = []
    for frame in manifest["source_frames"]:
        choices = [(priority, abs(frame["time"] - t), reason) for priority, t, reason in priorities if abs(frame["time"] - t) <= radius]
        if choices and frame["index"] not in chosen:
            priority, distance, reason = min(choices)
            candidates.append((priority, distance, frame["index"], reason))
    available = max(0, cap - len(chosen))
    chosen.update(x[2] for x in sorted(candidates)[:available])
    frames = export_frames(manifest["source"], manifest, chosen, Path(media_dir) / "frames",
                           settings.get("max_frame_width"), settings.get("jpeg_quality", 90))
    sizes = {f["index"]: 4 * ((Path(media_dir, f["file"]).stat().st_size + 2) // 3) for f in frames}
    selected = set(base_indices)
    used_bytes = sum(sizes[i] for i in selected)
    if image_byte_budget is not None and used_bytes > image_byte_budget:
        raise ValueError("Base frames exceed review request budget; use a new run with shorter windows or smaller frames")
    for _, _, index, _ in sorted(candidates)[:available]:
        if image_byte_budget is None or used_bytes + sizes[index] <= image_byte_budget:
            selected.add(index)
            used_bytes += sizes[index]
    frames = [f for f in frames if f["index"] in selected]
    plan = {"frames": frames, "targets": [{"priority": p, "time": t, "reason": r} for p, t, r in sorted(priorities)],
            "radius_seconds": radius, "base_frames": len(manifest["frames"]), "review_frames": len(frames),
            "omitted_dense_frames": len(candidates) - (len(selected) - len(base_indices)),
            "image_base64_bytes": used_bytes, "image_byte_budget": image_byte_budget,
            "note": "Additional frames are actual source frames; no interpolation. Omitted neighborhoods are not certified reviewed."}
    write_json(Path(media_dir) / "review_plan.json", plan)
    return plan
