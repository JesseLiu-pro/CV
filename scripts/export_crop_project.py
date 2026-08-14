from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2


ASPECT = 4 / 3
OUTPUT_SIZE = (960, 720)
FFMPEG = Path(r"C:\Users\work\anaconda3\envs\emg2pose\Library\bin\ffmpeg.exe")


@dataclass
class Keyframe:
    frame: int
    cx: float
    cy: float
    width: float


def resolve_video(project_path: Path, payload: dict) -> Path:
    saved = Path(payload.get("video", ""))
    if saved.exists():
        return saved
    project_name = project_path.name
    if project_name.endswith(".crop.json"):
        sibling = project_path.with_name(project_name.removesuffix(".crop.json") + ".mp4")
        if sibling.exists():
            return sibling
    raise FileNotFoundError("Cannot locate the source video saved in the crop project.")


def interpolate(keys: list[Keyframe], frame: int) -> Keyframe:
    if frame <= keys[0].frame:
        key = keys[0]
        return Keyframe(frame, key.cx, key.cy, key.width)
    if frame >= keys[-1].frame:
        key = keys[-1]
        return Keyframe(frame, key.cx, key.cy, key.width)
    for left, right in zip(keys, keys[1:]):
        if left.frame <= frame <= right.frame:
            amount = (frame - left.frame) / (right.frame - left.frame)
            amount = amount * amount * (3 - 2 * amount)
            return Keyframe(
                frame,
                left.cx + (right.cx - left.cx) * amount,
                left.cy + (right.cy - left.cy) * amount,
                left.width + (right.width - left.width) * amount,
            )
    return keys[-1]


def bounds(key: Keyframe, source_w: int, source_h: int) -> tuple[int, int, int, int]:
    width = min(max(96.0, key.width), source_w, source_h * ASPECT)
    height = width / ASPECT
    cx = min(max(key.cx, width / 2), source_w - width / 2)
    cy = min(max(key.cy, height / 2), source_h - height / 2)
    x1 = int(round(cx - width / 2))
    y1 = int(round(cy - height / 2))
    x2 = int(round(cx + width / 2))
    y2 = int(round(cy + height / 2))
    return x1, y1, x2, y2


def export(project_path: Path, output_path: Path) -> None:
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    video_path = resolve_video(project_path, payload)
    keys = sorted((Keyframe(**item) for item in payload["keyframes"]), key=lambda item: item.frame)
    if not keys:
        raise ValueError("The crop project has no keyframes.")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    command = [
        str(FFMPEG), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{OUTPUT_SIZE[0]}x{OUTPUT_SIZE[1]}", "-r", f"{fps:.8f}", "-i", "-", "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        frame = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            key = interpolate(keys, frame)
            x1, y1, x2, y2 = bounds(key, source_w, source_h)
            cropped = image[y1:y2, x1:x2]
            resized = cv2.resize(cropped, OUTPUT_SIZE, interpolation=cv2.INTER_LANCZOS4)
            assert process.stdin is not None
            try:
                process.stdin.write(resized.tobytes())
            except OSError as error:
                assert process.stderr is not None
                details = process.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(details or str(error)) from error
            frame += 1
            if frame % 120 == 0:
                print(f"Exporting {frame}/{frame_count} frames...", flush=True)
        assert process.stdin is not None
        process.stdin.close()
        code = process.wait()
        if code:
            assert process.stderr is not None
            raise RuntimeError(process.stderr.read().decode("utf-8", errors="replace"))
    finally:
        cap.release()
        if process.poll() is None:
            process.kill()
    print(f"Exported: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a 4:3 keyframe crop project.")
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.project.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
