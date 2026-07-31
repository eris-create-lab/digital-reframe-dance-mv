#!/usr/bin/env python3
import argparse
import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path


def probe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,nb_frames", "-of", "json", str(path)
    ], text=True)
    s = json.loads(raw)["streams"][0]
    return Fraction(s["r_frame_rate"]), int(s["nb_frames"])


def esc(text):
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("original")
    p.add_argument("edited")
    p.add_argument("output")
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--left-label", default="ORIGINAL")
    p.add_argument("--right-label", default="GPT EDIT")
    p.add_argument("--font")
    args = p.parse_args()

    original, edited, output = map(lambda x: Path(x).resolve(), (args.original, args.edited, args.output))
    fps0, frames0 = probe(original)
    fps1, frames1 = probe(edited)
    if fps0 != fps1:
        raise ValueError("input fps values must match")
    fps = float(fps0)
    pause_frames = round(args.pause * fps)
    total_frames = frames0 + pause_frames + frames1 + pause_frames
    right_start = frames0 + pause_frames
    right_end = right_start + frames1
    font = f"fontfile={Path(args.font).resolve()}:" if args.font else "font='DejaVu Sans':"
    left_label, right_label = esc(args.left_label), esc(args.right_label)
    if not args.font and (not left_label.isascii() or not right_label.isascii()):
        raise ValueError("non-ASCII labels require --font with a compatible font file")

    graph = f"""
[0:v]fps={fps},trim=end_frame={frames0},setpts=PTS-STARTPTS,scale=540:948:force_original_aspect_ratio=decrease:flags=lanczos,pad=540:948:(ow-iw)/2:(oh-ih)/2:black,setsar=1,tpad=stop={pause_frames+frames1+pause_frames}:stop_mode=clone[left];
[1:v]fps={fps},trim=end_frame={frames1},setpts=PTS-STARTPTS,scale=540:948:force_original_aspect_ratio=decrease:flags=lanczos,pad=540:948:(ow-iw)/2:(oh-ih)/2:black,setsar=1,tpad=start={right_start}:start_mode=clone:stop={pause_frames}:stop_mode=clone[right];
[left][right]hstack=inputs=2,pad=1080:1080:0:76:color=0x11141c,
drawbox=x=540:y=76:w=540:h=948:color=black@0.28:t=fill:enable='lt(n,{right_start})+gte(n,{right_end})',
drawbox=x=0:y=76:w=540:h=948:color=black@0.28:t=fill:enable='gte(n,{frames0})',
drawbox=x=0:y=76:w=540:h=948:color=0x48d7ff@0.95:t=5:enable='lt(n,{frames0})',
drawbox=x=540:y=76:w=540:h=948:color=0xff4f9a@0.95:t=5:enable='between(n,{right_start},{right_end-1})',
drawbox=x=539:y=76:w=2:h=948:color=white@0.55:t=fill,
drawtext={font}text='{left_label}':fontcolor=white:fontsize=36:x=(540-text_w)/2:y=17,
drawtext={font}text='{right_label}':fontcolor=white:fontsize=36:x=540+(540-text_w)/2:y=17,
format=yuv420p,trim=end_frame={total_frames},settb=expr=1/{fps},setpts=N[outv];
[0:a]atrim=end={frames0/fps},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a0];
anullsrc=r=48000:cl=stereo:d={args.pause}[s0];
[1:a]atrim=end={frames1/fps},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a1];
anullsrc=r=48000:cl=stereo:d={args.pause}[s1];
[a0][s0][a1][s1]concat=n=4:v=0:a=1[outa]
""".strip()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(graph)
        filter_path = f.name
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(original), "-i", str(edited),
        "-filter_complex_script", filter_path, "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-fps_mode", "passthrough",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)
    ], check=True)
    out_fps, out_frames = probe(output)
    if out_fps != fps0 or out_frames != total_frames:
        raise RuntimeError(f"comparison timing mismatch: {out_frames} frames at {out_fps}")
    print(output)


if __name__ == "__main__":
    main()

