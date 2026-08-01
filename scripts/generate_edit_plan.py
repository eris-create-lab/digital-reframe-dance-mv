#!/usr/bin/env python3
"""Turn analysis.json into a conservative Version 2.1 direction/edit plan."""

import argparse
import json
from pathlib import Path


KINDS = {
    "full_body": 1.00,
    "waist_up": 0.78,
    "bust_up": 0.62,
    "face_close_up": 0.44,
}


def center_at(track, time):
    if not track:
        return 0.5, 0.46
    item = min(track, key=lambda p: abs(float(p["time"]) - time))
    return float(item["x"]), float(item["y"])


def crop_for(kind, center, width, height):
    scale = KINDS[kind]
    crop_w = max(2, round(width * scale / 2) * 2)
    crop_h = max(2, round(height * scale / 2) * 2)
    cx, cy = center
    if kind == "face_close_up":
        cy = max(0.20, cy - 0.12)
    elif kind == "bust_up":
        cy = max(0.28, cy - 0.07)
    x = round(cx * width - crop_w / 2)
    y = round(cy * height - crop_h / 2)
    x = min(max(0, x), width - crop_w)
    y = min(max(0, y), height - crop_h)
    return {"x": int(x), "y": int(y), "w": int(crop_w), "h": int(crop_h)}


def choose_events(analysis):
    duration = analysis["metadata"]["duration"]
    audio = analysis["audio"]
    motion = analysis["video"]["motion_peaks"]
    candidates = []
    for p in audio.get("peaks", []):
        candidates.append((float(p["time"]), float(p["strength"]) * 1.15, "audio_peak"))
    for p in motion:
        candidates.append((float(p["time"]), float(p["strength"]), "motion_peak"))
    for t in audio.get("beats", []):
        candidates.append((float(t), 0.38, "beat"))
    candidates.sort(key=lambda item: item[1], reverse=True)
    chosen = []
    target = 3 if duration >= 9 else 2 if duration >= 5 else 1
    for time, strength, source in candidates:
        if time < 0.8 or time > duration - 0.65:
            continue
        if any(abs(time - old[0]) < 1.65 for old in chosen):
            continue
        chosen.append((time, strength, source))
        if len(chosen) == target:
            break
    if not chosen:
        chosen = [(duration * 0.55, 0.5, "duration_fallback")]
    return sorted(chosen)


def build_plan(analysis):
    meta, video, audio = analysis["metadata"], analysis["video"], analysis["audio"]
    fps, frames = float(meta["fps_float"]), int(meta["frames"])
    duration, width, height = float(meta["duration"]), int(meta["width"]), int(meta["height"])
    events = choose_events(analysis)
    motion_level = video["camera_motion_level"]
    style = "IMPACT" if len(audio.get("peaks", [])) >= 3 or motion_level == "high" else "CLEAN"
    kinds = ["waist_up", "bust_up", "face_close_up"] if style == "IMPACT" else ["waist_up", "bust_up", "waist_up"]
    accents = []
    for i, (time, strength, source) in enumerate(events):
        length = min(0.78, max(0.48, 0.52 + 0.20 * strength))
        start = max(1, round((time - 0.10) * fps))
        end = min(frames - 1, max(start + 2, round((time - 0.10 + length) * fps)))
        if accents and start < accents[-1][1] + round(0.75 * fps):
            continue
        accents.append((start, end, kinds[i % len(kinds)], time, source, strength))

    ranked = sorted(range(len(accents)), key=lambda i: accents[i][5], reverse=True)
    effect_roles = {}
    if style == "IMPACT" and ranked:
        effect_roles[ranked[0]] = "flash_exposure"
    if style == "IMPACT" and len(ranked) >= 2:
        effect_roles[ranked[1]] = "shake_blur"
    if style == "IMPACT" and len(ranked) >= 3:
        effect_roles[ranked[2]] = "speed_ramp"

    shots, cursor = [], 0
    for accent_index, (start, end, kind, time, source, strength) in enumerate(accents):
        if start > cursor:
            shots.append({"start_frame": cursor, "end_frame": start, "kind": "full_body"})
        c0 = center_at(video["subject_track"], start / fps)
        c1 = center_at(video["subject_track"], max(start / fps, (end - 1) / fps))
        crop = crop_for(kind, c0, width, height)
        end_crop = crop_for(kind, c1, width, height)
        transition = {}
        effects = {}
        role = effect_roles.get(accent_index)
        if role == "flash_exposure":
            transition["flash"] = 0.075
            effects["exposure"] = {"brightness": 0.035, "frames": 6}
        elif role == "shake_blur":
            effects["camera_shake"] = {"amplitude": 4, "frames": 6, "frequency": 1.9}
            effects["motion_blur"] = {"frames": 3, "sigma_x": 1.1, "sigma_y": 0.25}
        elif role == "speed_ramp":
            effects["speed_ramp"] = {"first_segment_ratio": 0.38, "first_speed": 1.35}

        shot = {
            "start_frame": start, "end_frame": end, "kind": kind,
            "crop": crop,
            "pan": {"x_end": end_crop["x"], "y_end": end_crop["y"]},
            "zoom": {"start": 1.0, "end": 1.035},
            "transition": transition,
            "effects": effects,
            "reason": f"{source}@{time:.3f}s",
        }
        shots.append(shot)
        cursor = end
    if cursor < frames:
        shots.append({"start_frame": cursor, "end_frame": frames, "kind": "full_body"})

    timeline = [
        {"time": round(s["start_frame"] / fps, 4), "action": s["kind"], "reason": s.get("reason", "rest")}
        for s in shots
    ]
    concept = [
        "ビートと動作ピークに同期した短いリフレーム",
        "全身ショットを主役として維持",
        "被写体を緩やかに追従",
    ]
    if effect_roles:
        concept.append("強いピークへFlash、Shake、Motion Blur、Speed Rampを分散配置")
    return {
        "schema_version": "2.1",
        "style": "dance_mv",
        "direction_style": style,
        "bpm": audio.get("bpm"),
        "editing_concept": concept,
        "timeline": timeline,
        "grade": {"contrast": 1.0, "saturation": 1.0, "gamma": 1.0, "unsharp": 0.0},
        "recipe": {
            "concept": style,
            "signature_techniques": ["tracking-reframe", "impact-effects-v2.1"],
            "notes": "自動解析結果から生成。顔アップは視覚レビューで再調整可能。",
        },
        "shots": shots,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a renderable edit plan from analysis JSON")
    parser.add_argument("analysis")
    parser.add_argument("output")
    args = parser.parse_args()
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    plan = build_plan(analysis)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
