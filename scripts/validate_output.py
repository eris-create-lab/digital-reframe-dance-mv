#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from fractions import Fraction


def video_info(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames,nb_read_frames,duration",
        "-of", "json", path
    ], text=True)
    s = json.loads(raw)["streams"][0]
    fps = Fraction(s["r_frame_rate"])
    frame_value = s.get("nb_frames") or s.get("nb_read_frames")
    frames = int(frame_value) if frame_value and frame_value != "N/A" else round(float(s["duration"]) * float(fps))
    return {
        "width": int(s["width"]), "height": int(s["height"]),
        "fps": str(fps), "frames": frames,
        "duration": float(s["duration"])
    }


def audio_md5(path):
    p = subprocess.run([
        "ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-c", "copy", "-f", "md5", "-"
    ], text=True, capture_output=True)
    return p.stdout.strip() if p.returncode == 0 else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("output")
    p.add_argument("--allow-audio-change", action="store_true")
    args = p.parse_args()

    source, output = video_info(args.source), video_info(args.output)
    checks = {
        "dimensions": (source["width"], source["height"]) == (output["width"], output["height"]),
        "fps": source["fps"] == output["fps"],
        "frames": source["frames"] == output["frames"],
        "duration": abs(source["duration"] - output["duration"]) <= 1 / float(Fraction(source["fps"])),
    }
    if not args.allow_audio_change:
        checks["audio"] = audio_md5(args.source) == audio_md5(args.output)

    print(json.dumps({"source": source, "output": output, "checks": checks}, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
