#!/usr/bin/env python3
"""Analyze a dance video with only ffmpeg, NumPy and SciPy.

The output is deliberately model-free so it runs in ChatGPT Work without
downloading weights.  Motion saliency supplies a conservative subject track;
the calling agent can refine face/person framing after inspecting the contact
sheet when visual reasoning is available.
"""

import argparse
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks


def ffprobe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ], text=True)
    data = json.loads(raw)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    fps = Fraction(video.get("avg_frame_rate") or video["r_frame_rate"])
    duration = float(video.get("duration") or data["format"]["duration"])
    frames = int(video.get("nb_frames") or round(duration * float(fps)))
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": f"{fps.numerator}/{fps.denominator}",
        "fps_float": float(fps),
        "frames": frames,
        "duration": duration,
        "video_codec": video.get("codec_name"),
        "has_audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
    }


def decode_gray(path, width, height, analysis_fps):
    scale_w = min(192, width)
    scale_h = max(2, round(height * scale_w / width / 2) * 2)
    proc = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(path), "-an",
        "-vf", f"fps={analysis_fps:.8f},scale={scale_w}:{scale_h}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ], capture_output=True, check=True)
    frame_size = scale_w * scale_h
    count = len(proc.stdout) // frame_size
    if not count:
        raise RuntimeError("no video frames decoded")
    frames = np.frombuffer(proc.stdout[:count * frame_size], dtype=np.uint8)
    return frames.reshape(count, scale_h, scale_w).astype(np.float32) / 255.0


def weighted_center(weight):
    total = float(weight.sum())
    h, w = weight.shape
    if total < 1e-7:
        return 0.5, 0.46
    ys, xs = np.indices(weight.shape)
    return float((weight * xs).sum() / total / max(1, w - 1)), float((weight * ys).sum() / total / max(1, h - 1))


def analyze_frames(frames, analysis_fps):
    differences = np.mean(np.abs(np.diff(frames, axis=0)), axis=(1, 2))
    differences = np.pad(differences, (1, 0))
    median = float(np.median(differences))
    mad = float(np.median(np.abs(differences - median))) + 1e-6
    scene_threshold = max(0.18, median + 8.0 * mad)
    scene_idx, _ = find_peaks(differences, height=scene_threshold, distance=max(1, round(analysis_fps * 0.4)))

    # Motion is the safest model-free locator for a dancer.  A mild centre
    # prior prevents background screens and hard frame edges from taking over.
    h, w = frames.shape[1:]
    yy, xx = np.indices((h, w))
    prior = np.exp(-(((xx / max(1, w - 1) - 0.5) / 0.43) ** 2 + ((yy / max(1, h - 1) - 0.48) / 0.48) ** 2))
    centers = []
    prev = frames[0]
    smooth_x, smooth_y = 0.5, 0.46
    for i, frame in enumerate(frames):
        motion = np.abs(frame - prev)
        gx = np.abs(np.diff(frame, axis=1, prepend=frame[:, :1]))
        gy = np.abs(np.diff(frame, axis=0, prepend=frame[:1, :]))
        saliency = (motion * 2.0 + (gx + gy) * 0.18) * prior
        x, y = weighted_center(saliency)
        smooth_x = 0.82 * smooth_x + 0.18 * x
        smooth_y = 0.82 * smooth_y + 0.18 * y
        centers.append({"time": round(i / analysis_fps, 4), "x": round(smooth_x, 4), "y": round(smooth_y, 4)})
        prev = frame

    motion_norm = differences / max(1e-6, float(np.percentile(differences, 95)))
    motion_peaks, _ = find_peaks(motion_norm, height=0.45, distance=max(1, round(analysis_fps * 0.22)))
    mean_motion = float(np.mean(differences))
    camera_level = "high" if mean_motion > 0.085 else "medium" if mean_motion > 0.035 else "low"
    return {
        "analysis_fps": analysis_fps,
        "scene_changes": [round(float(i / analysis_fps), 4) for i in scene_idx],
        "motion_peaks": [
            {"time": round(float(i / analysis_fps), 4), "strength": round(float(min(1.0, motion_norm[i])), 4)}
            for i in motion_peaks
        ],
        "mean_frame_motion": round(mean_motion, 6),
        "camera_motion_level": camera_level,
        "subject_track": centers,
        "subject_tracking_method": "motion_edge_saliency",
        "person_detection": {"status": "heuristic_track", "count": 1},
        "face_detection": {"status": "visual_review_recommended"},
    }


def decode_audio(path, rate=22050):
    proc = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
        "-ar", str(rate), "-f", "f32le", "-",
    ], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype="<f4").astype(np.float64)


def analyze_audio(samples, rate, duration):
    if samples is None or len(samples) < rate // 2:
        return {
            "available": False, "bpm": None, "beats": [], "peaks": [],
            "chorus_candidate": None, "mean_loudness": None,
        }
    hop, window = 512, 2048
    usable = max(1, 1 + (len(samples) - window) // hop)
    rms = np.empty(usable)
    flux = np.empty(usable)
    prev_spec = np.zeros(window // 2 + 1)
    hann = np.hanning(window)
    for i in range(usable):
        chunk = samples[i * hop:i * hop + window]
        if len(chunk) < window:
            chunk = np.pad(chunk, (0, window - len(chunk)))
        rms[i] = math.sqrt(float(np.mean(chunk * chunk)) + 1e-12)
        spec = np.abs(np.fft.rfft(chunk * hann))
        flux[i] = float(np.maximum(0, spec - prev_spec).sum())
        prev_spec = spec
    onset = flux / (np.percentile(flux, 95) + 1e-12)
    env_rate = rate / hop
    min_lag = max(1, round(env_rate * 60 / 180))
    max_lag = min(len(onset) - 1, round(env_rate * 60 / 60))
    centered = onset - np.mean(onset)
    corr = np.correlate(centered, centered, mode="full")[len(centered) - 1:]
    bpm = None
    beats = []
    if max_lag > min_lag:
        lag = min_lag + int(np.argmax(corr[min_lag:max_lag + 1]))
        bpm_value = 60.0 * env_rate / lag
        # Autocorrelation often reports half-time for dance music. Prefer the
        # actionable editing range while retaining genuinely slower material.
        if bpm_value < 90.0 and bpm_value * 2.0 <= 180.0:
            bpm_value *= 2.0
            lag = max(1, round(60.0 * env_rate / bpm_value))
        bpm = round(bpm_value, 2)
        phase_scores = [float(onset[p::lag].sum()) for p in range(lag)]
        phase = int(np.argmax(phase_scores))
        beats = [round(float((phase + i * lag) / env_rate), 4) for i in range(math.ceil((len(onset) - phase) / lag))]
        beats = [t for t in beats if t <= duration + 0.05]
    peak_idx, props = find_peaks(onset, height=0.45, distance=max(1, round(env_rate * 0.12)))
    peaks = [
        {"time": round(float(i / env_rate), 4), "strength": round(float(min(1.0, h)), 4)}
        for i, h in zip(peak_idx, props.get("peak_heights", []))
    ]
    chorus_window = max(1, round(env_rate * min(4.0, max(1.0, duration / 3))))
    energy = np.convolve(rms, np.ones(chorus_window) / chorus_window, mode="same")
    chorus = max(0.0, min(duration, float(np.argmax(energy) / env_rate - chorus_window / env_rate / 2)))
    return {
        "available": True,
        "bpm": bpm,
        "beats": beats,
        "peaks": peaks,
        "chorus_candidate": round(chorus, 4),
        "mean_loudness": round(float(np.mean(rms)), 6),
        "peak_loudness": round(float(np.max(rms)), 6),
    }


def analyze(path):
    meta = ffprobe(path)
    analysis_fps = min(12.0, meta["fps_float"])
    frames = decode_gray(path, meta["width"], meta["height"], analysis_fps)
    video = analyze_frames(frames, analysis_fps)
    audio = analyze_audio(decode_audio(path), 22050, meta["duration"]) if meta["has_audio"] else analyze_audio(None, 22050, meta["duration"])
    return {"schema_version": "2.0", "source": str(Path(path).resolve()), "metadata": meta, "video": video, "audio": audio}


def main():
    parser = argparse.ArgumentParser(description="Analyze video, motion, subject position and music structure")
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    result = analyze(Path(args.input).resolve())
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
