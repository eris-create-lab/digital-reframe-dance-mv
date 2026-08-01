#!/usr/bin/env python3
"""One-command MP4 -> analysis -> direction -> edit -> validation pipeline."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(command):
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description="Automatically direct and edit a dance MP4")
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--work-dir")
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    scripts = Path(__file__).resolve().parent
    source = Path(args.input).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    output = Path(args.output).resolve() if args.output else source.with_name(f"{source.stem}_directed.mp4")
    if output == source:
        raise ValueError("output must not overwrite the input video")
    work = Path(args.work_dir).resolve() if args.work_dir else output.with_name(f"{output.stem}_work")
    work.mkdir(parents=True, exist_ok=True)
    analysis = work / "analysis.json"
    plan = work / "direction.json"
    validation = work / "validation.json"

    run([sys.executable, str(scripts / "probe_video.py"), str(source), "--out-dir", str(work), "--samples", "18"])
    run([sys.executable, str(scripts / "analyze_video.py"), str(source), str(analysis)])
    run([sys.executable, str(scripts / "generate_edit_plan.py"), str(analysis), str(plan)])
    run([sys.executable, str(scripts / "render_reframe.py"), str(source), str(plan), str(output), "--crf", str(args.crf)])
    result = subprocess.run([
        sys.executable, str(scripts / "validate_output.py"), str(source), str(output),
    ], text=True, capture_output=True)
    validation.write_text(result.stdout or result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"output validation failed; see {validation}")

    print(json.dumps({
        "output": str(output), "analysis": str(analysis),
        "direction": str(plan), "validation": str(validation),
        "contact_sheet": str(work / "contact.jpg"),
        "waveform": str(work / "waveform.png") if (work / "waveform.png").exists() else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
