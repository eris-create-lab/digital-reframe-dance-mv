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
        "-count_frames", "-show_entries", "stream=width,height,r_frame_rate,nb_frames,nb_read_frames,duration",
        "-of", "json", str(path)
    ], text=True)
    stream = json.loads(raw)["streams"][0]
    fps = Fraction(stream["r_frame_rate"])
    frame_value = stream.get("nb_frames") or stream.get("nb_read_frames")
    frames = int(frame_value) if frame_value and frame_value != "N/A" else round(float(stream["duration"]) * float(fps))
    duration = float(stream.get("duration") or frames / float(fps))
    return int(stream["width"]), int(stream["height"]), fps, frames, duration


def has_audio(path):
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)
    ], text=True).strip()
    return bool(value)


def validate_plan(plan, width, height, frames):
    shots = plan.get("shots", [])
    if not shots or shots[0]["start_frame"] != 0 or shots[-1]["end_frame"] != frames:
        raise ValueError("shots must cover frame 0 through the final input frame")
    cursor = 0
    for shot in shots:
        start, end = int(shot["start_frame"]), int(shot["end_frame"])
        if start != cursor or end <= start:
            raise ValueError("shots must be contiguous and non-empty")
        cursor = end
        crop = shot.get("crop")
        if crop:
            x, y, w, h = (int(crop[k]) for k in ("x", "y", "w", "h"))
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
                raise ValueError(f"crop outside source bounds: {crop}")


def build_filter(plan, width, height, frames, duration):
    grade = plan.get("grade", {})
    contrast = float(grade.get("contrast", 1.0))
    saturation = float(grade.get("saturation", 1.0))
    gamma = float(grade.get("gamma", 1.0))
    unsharp = float(grade.get("unsharp", 0.0))
    shots = plan["shots"]
    lines = [
        f"[0:v]format=yuv420p,eq=contrast={contrast}:saturation={saturation}:gamma={gamma},"
        f"unsharp=5:5:{unsharp},split={len(shots)}" + "".join(f"[v{i}]" for i in range(len(shots))) + ";"
    ]

    for i, shot in enumerate(shots):
        start, end = int(shot["start_frame"]), int(shot["end_frame"])
        length = end - start
        chain = f"[v{i}]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS"
        crop = shot.get("crop")
        if crop:
            x0, y0, cw, ch = (int(crop[k]) for k in ("x", "y", "w", "h"))
            pan = shot.get("pan", {})
            x1, y1 = int(pan.get("x_end", x0)), int(pan.get("y_end", y0))
            denom = max(1, length - 1)
            chain += f",crop={cw}:{ch}:x='{x0}+({x1-x0})*n/{denom}':y='{y0}+({y1-y0})*n/{denom}'"
            chain += f",scale={width}:{height}:flags=lanczos"

        zoom = shot.get("zoom")
        if zoom:
            z0, z1 = float(zoom.get("start", 1.0)), float(zoom.get("end", 1.0))
            denom = max(1, length - 1)
            zexpr = f"{z0}+({z1-z0})*(1-cos(PI*n/{denom}))/2"
            chain += (
                f",scale=w='trunc({width}*({zexpr})/2)*2':h='trunc({height}*({zexpr})/2)*2':eval=frame:flags=lanczos"
                f",crop={width}:{height}:(iw-{width})/2:(ih-{height})/2"
            )

        trans = shot.get("transition", {})
        blur_frames = int(trans.get("blur_frames", 0))
        if blur_frames:
            chain += f",gblur=sigma=4:steps=2:enable='lt(n,{blur_frames})'"
        rgb = int(trans.get("rgb_shift", 0))
        if rgb:
            chain += f",rgbashift=rh={rgb}:bh={-rgb}:enable='lt(n,2)'"
        flash = float(trans.get("flash", 0.0))
        if flash:
            chain += f",eq=brightness='if(eq(n,0),{flash},if(eq(n,1),{flash*0.35},0))':eval=frame"
        chain += f",setsar=1[o{i}];"
        lines.append(chain)

    inputs = "".join(f"[o{i}]" for i in range(len(shots)))
    frame_interval = duration / frames
    lines.append(
        f"{inputs}concat=n={len(shots)}:v=1:a=0,"
        f"setpts=N*{frame_interval:.12f}/TB,format=yuv420p[outv]"
    )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("plan")
    p.add_argument("output")
    p.add_argument("--crf", type=int, default=18)
    args = p.parse_args()

    src, output = Path(args.input).resolve(), Path(args.output).resolve()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    width, height, fps, frames, duration = probe(src)
    validate_plan(plan, width, height, frames)
    graph = build_filter(plan, width, height, frames, duration)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(graph)
        filter_path = f.name

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-filter_complex_script", filter_path, "-map", "[outv]"
    ]
    if has_audio(src):
        cmd += ["-map", "0:a:0", "-c:a", "copy"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
        "-fps_mode", "passthrough", "-movflags", "+faststart", str(output)
    ]
    subprocess.run(cmd, check=True)

    _, _, out_fps, out_frames, _ = probe(output)
    if out_fps != fps or out_frames != frames:
        raise RuntimeError(f"frame mismatch: input={frames}@{fps}, output={out_frames}@{out_fps}")
    print(output)


if __name__ == "__main__":
    main()
