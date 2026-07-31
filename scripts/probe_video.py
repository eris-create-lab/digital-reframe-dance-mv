#!/usr/bin/env python3
import argparse
import json
import math
import subprocess
from pathlib import Path


def run(cmd):
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--samples", type=int, default=15)
    args = p.parse_args()

    src = Path(args.input).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(src)
    ], text=True)
    info = json.loads(raw)
    (out / "metadata.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    duration = float(info["format"]["duration"])
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    width, height = int(video["width"]), int(video["height"])
    cols = 5
    rows = math.ceil(args.samples / cols)
    sample_fps = args.samples / duration
    thumb_w = min(240, width)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-vf", f"fps={sample_fps:.8f},scale={thumb_w}:-2,tile={cols}x{rows}:padding=4:margin=4",
        "-frames:v", "1", str(out / "contact.jpg")
    ])

    if any(s["codec_type"] == "audio" for s in info["streams"]):
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-filter_complex", "showwavespic=s=1200x240:colors=0x48d7ff",
            "-frames:v", "1", str(out / "waveform.png")
        ])

    print(out / "metadata.json")
    print(out / "contact.jpg")
    if (out / "waveform.png").exists():
        print(out / "waveform.png")


if __name__ == "__main__":
    main()

