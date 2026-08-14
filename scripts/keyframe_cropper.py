from __future__ import annotations

import json
import math
import subprocess
import threading
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np


ASPECT = 4 / 3
PREVIEW_MAX = (960, 610)
OUTPUT_SIZE = (960, 720)
FFMPEG = Path(r"C:\Users\work\anaconda3\envs\emg2pose\Library\bin\ffmpeg.exe")
DEFAULT_VIDEO = Path(r"C:\Users\work\Desktop\媒体1.mp4")


@dataclass
class Keyframe:
    frame: int
    cx: float
    cy: float
    width: float


class CropperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("4:3 Keyframe Video Cropper")
        self.root.minsize(980, 760)

        self.video_path: Path | None = None
        self.cap: cv2.VideoCapture | None = None
        self.fps = 30.0
        self.frame_count = 1
        self.source_w = 1
        self.source_h = 1
        self.current_frame = 0
        self.current_image: np.ndarray | None = None
        self.keyframes: list[Keyframe] = []
        self.crop = Keyframe(0, 0.5, 0.5, 0.6)

        self.display_scale = 1.0
        self.display_x = 0.0
        self.display_y = 0.0
        self.display_w = 1.0
        self.display_h = 1.0
        self.drag_mode: str | None = None
        self.drag_start = (0.0, 0.0)
        self.drag_crop: Keyframe | None = None
        self.photo: tk.PhotoImage | None = None
        self.exporting = False

        self._build_ui()
        self.root.bind("<Left>", lambda _: self.step(-1))
        self.root.bind("<Right>", lambda _: self.step(1))
        self.root.bind("<Shift-Left>", lambda _: self.step(-10))
        self.root.bind("<Shift-Right>", lambda _: self.step(10))
        self.root.bind("<Control-s>", lambda _: self.save_project())
        self.root.bind("<space>", lambda _: self.add_keyframe())

        if DEFAULT_VIDEO.exists():
            self.open_video(DEFAULT_VIDEO)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(12, 10))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="打开视频", command=self.choose_video).pack(side="left")
        ttk.Button(toolbar, text="保存关键帧", command=self.save_project).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="载入关键帧", command=self.load_project).pack(side="left", padx=(8, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(toolbar, text="添加 / 更新关键帧  Space", command=self.add_keyframe).pack(side="left")
        ttk.Button(toolbar, text="删除关键帧", command=self.delete_keyframe).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="导出 4:3 视频", command=self.export_video).pack(side="right")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12)

        preview_panel = ttk.Frame(body)
        side_panel = ttk.Frame(body, width=235)
        body.add(preview_panel, weight=5)
        body.add(side_panel, weight=1)

        self.canvas = tk.Canvas(preview_panel, bg="#171b18", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.render())
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_wheel)

        ttk.Label(side_panel, text="关键帧", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(4, 8))
        self.key_list = tk.Listbox(side_panel, exportselection=False, height=18)
        self.key_list.pack(fill="both", expand=True)
        self.key_list.bind("<<ListboxSelect>>", self.select_keyframe)
        ttk.Label(
            side_panel,
            text="拖动画框：移动\n拖动四角：缩放\n鼠标滚轮：缩放\n← →：逐帧\nShift + ← →：10 帧",
            foreground="#59615c",
            justify="left",
        ).pack(anchor="w", pady=12)

        timeline = ttk.Frame(self.root, padding=12)
        timeline.pack(fill="x")
        self.time_label = ttk.Label(timeline, text="00:00.000 / 00:00.000", width=24)
        self.time_label.pack(side="left")
        self.scale_var = tk.DoubleVar(value=0)
        self.timeline = ttk.Scale(timeline, from_=0, to=1, variable=self.scale_var, command=self.on_scrub)
        self.timeline.pack(side="left", fill="x", expand=True, padx=10)
        self.frame_label = ttk.Label(timeline, text="Frame 0", width=14, anchor="e")
        self.frame_label.pack(side="right")

        self.marker_canvas = tk.Canvas(self.root, height=16, bg="#f0f0ed", highlightthickness=0)
        self.marker_canvas.pack(fill="x", padx=12)
        self.marker_canvas.bind("<Button-1>", self.click_marker)
        self.marker_canvas.bind("<Configure>", lambda _: self.draw_markers())

        status = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_label = ttk.Label(status, text="打开视频后开始调整", width=32, anchor="e")
        self.status_label.pack(side="right", padx=(10, 0))

    def choose_video(self) -> None:
        filename = filedialog.askopenfilename(
            title="选择视频",
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi"), ("All files", "*.*")],
        )
        if filename:
            self.open_video(Path(filename))

    def open_video(self, path: Path) -> None:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            messagebox.showerror("无法打开", f"无法读取视频：\n{path}")
            return
        if self.cap:
            self.cap.release()
        self.cap = cap
        self.video_path = path
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        max_width = min(self.source_w, self.source_h * ASPECT)
        self.crop = Keyframe(0, self.source_w / 2, self.source_h / 2, max_width * 0.76)
        self.keyframes = []
        self.timeline.configure(to=self.frame_count - 1)
        self.seek(0)
        self.refresh_key_list()
        self.status_label.configure(text=f"{self.source_w}x{self.source_h} · {self.fps:.2f} fps")

    def seek(self, frame: int) -> None:
        if not self.cap:
            return
        frame = max(0, min(self.frame_count - 1, int(frame)))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, image = self.cap.read()
        if not ok:
            return
        self.current_frame = frame
        self.current_image = image
        self.crop = self.interpolated_crop(frame)
        self.scale_var.set(frame)
        self.update_labels()
        self.render()

    def on_scrub(self, value: str) -> None:
        frame = int(round(float(value)))
        if frame != self.current_frame:
            self.seek(frame)

    def step(self, delta: int) -> None:
        self.seek(self.current_frame + delta)

    def update_labels(self) -> None:
        current = self.current_frame / self.fps
        total = (self.frame_count - 1) / self.fps
        self.time_label.configure(text=f"{self.format_time(current)} / {self.format_time(total)}")
        self.frame_label.configure(text=f"Frame {self.current_frame}")

    @staticmethod
    def format_time(seconds: float) -> str:
        minutes = int(seconds // 60)
        remainder = seconds - minutes * 60
        return f"{minutes:02d}:{remainder:06.3f}"

    def interpolated_crop(self, frame: int) -> Keyframe:
        if not self.keyframes:
            return Keyframe(frame, self.crop.cx, self.crop.cy, self.crop.width)
        keys = sorted(self.keyframes, key=lambda item: item.frame)
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
        return Keyframe(frame, self.crop.cx, self.crop.cy, self.crop.width)

    def crop_bounds(self, crop: Keyframe) -> tuple[float, float, float, float]:
        width = min(crop.width, self.source_w, self.source_h * ASPECT)
        width = max(96.0, width)
        height = width / ASPECT
        cx = min(max(crop.cx, width / 2), self.source_w - width / 2)
        cy = min(max(crop.cy, height / 2), self.source_h - height / 2)
        return cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2

    def normalize_crop(self) -> None:
        x1, y1, x2, y2 = self.crop_bounds(self.crop)
        self.crop.cx = (x1 + x2) / 2
        self.crop.cy = (y1 + y2) / 2
        self.crop.width = x2 - x1

    def render(self) -> None:
        if self.current_image is None:
            return
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        scale = min(canvas_w / self.source_w, canvas_h / self.source_h)
        display_w = max(1, int(self.source_w * scale))
        display_h = max(1, int(self.source_h * scale))
        self.display_scale = scale
        self.display_w = display_w
        self.display_h = display_h
        self.display_x = (canvas_w - display_w) / 2
        self.display_y = (canvas_h - display_h) / 2

        rgb = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (display_w, display_h), interpolation=cv2.INTER_AREA)
        header = f"P6 {display_w} {display_h} 255 ".encode("ascii")
        self.photo = tk.PhotoImage(data=header + rgb.tobytes(), format="PPM")
        self.canvas.delete("all")
        self.canvas.create_image(self.display_x, self.display_y, image=self.photo, anchor="nw")

        x1, y1, x2, y2 = self.crop_bounds(self.crop)
        dx1, dy1 = self.source_to_canvas(x1, y1)
        dx2, dy2 = self.source_to_canvas(x2, y2)
        image_left, image_top = self.display_x, self.display_y
        image_right = image_left + self.display_w
        image_bottom = image_top + self.display_h
        shade = {"fill": "#101411", "stipple": "gray50", "outline": ""}
        self.canvas.create_rectangle(image_left, image_top, image_right, dy1, **shade)
        self.canvas.create_rectangle(image_left, dy2, image_right, image_bottom, **shade)
        self.canvas.create_rectangle(image_left, dy1, dx1, dy2, **shade)
        self.canvas.create_rectangle(dx2, dy1, image_right, dy2, **shade)
        self.canvas.create_rectangle(dx1, dy1, dx2, dy2, outline="#f4f1df", width=3)

        handle = 7
        for x, y in ((dx1, dy1), (dx2, dy1), (dx1, dy2), (dx2, dy2)):
            self.canvas.create_rectangle(x - handle, y - handle, x + handle, y + handle, fill="#f4f1df", outline="#172219")
        self.canvas.create_text(dx1 + 12, dy1 + 12, text="4:3", anchor="nw", fill="white", font=("Segoe UI", 11, "bold"))

    def source_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return self.display_x + x * self.display_scale, self.display_y + y * self.display_scale

    def canvas_to_source(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.display_x) / self.display_scale, (y - self.display_y) / self.display_scale

    def hit_test(self, x: float, y: float) -> str | None:
        x1, y1, x2, y2 = self.crop_bounds(self.crop)
        dx1, dy1 = self.source_to_canvas(x1, y1)
        dx2, dy2 = self.source_to_canvas(x2, y2)
        threshold = 18
        corners = {"nw": (dx1, dy1), "ne": (dx2, dy1), "sw": (dx1, dy2), "se": (dx2, dy2)}
        for name, (hx, hy) in corners.items():
            if math.hypot(x - hx, y - hy) <= threshold:
                return name
        if dx1 <= x <= dx2 and dy1 <= y <= dy2:
            return "move"
        return None

    def on_press(self, event: tk.Event) -> None:
        self.drag_mode = self.hit_test(event.x, event.y)
        self.drag_start = self.canvas_to_source(event.x, event.y)
        self.drag_crop = Keyframe(self.current_frame, self.crop.cx, self.crop.cy, self.crop.width)

    def on_drag(self, event: tk.Event) -> None:
        if not self.drag_mode or not self.drag_crop:
            return
        sx, sy = self.canvas_to_source(event.x, event.y)
        start_x, start_y = self.drag_start
        if self.drag_mode == "move":
            self.crop.cx = self.drag_crop.cx + sx - start_x
            self.crop.cy = self.drag_crop.cy + sy - start_y
        else:
            opposite_x = self.drag_crop.cx + (self.drag_crop.width / 2) * (-1 if "e" in self.drag_mode else 1)
            new_width = abs(sx - opposite_x)
            self.crop.width = new_width
            self.crop.cx = (sx + opposite_x) / 2
            height = new_width / ASPECT
            opposite_y = self.drag_crop.cy + (self.drag_crop.width / ASPECT / 2) * (-1 if "s" in self.drag_mode else 1)
            self.crop.cy = opposite_y + (height / 2) * (1 if "s" in self.drag_mode else -1)
        self.normalize_crop()
        self.render()

    def on_release(self, _: tk.Event) -> None:
        self.drag_mode = None
        self.drag_crop = None

    def on_wheel(self, event: tk.Event) -> None:
        factor = 0.94 if event.delta > 0 else 1.06
        self.crop.width *= factor
        self.normalize_crop()
        self.render()

    def add_keyframe(self) -> None:
        if not self.cap:
            return
        new_key = Keyframe(self.current_frame, self.crop.cx, self.crop.cy, self.crop.width)
        for index, key in enumerate(self.keyframes):
            if key.frame == self.current_frame:
                self.keyframes[index] = new_key
                break
        else:
            self.keyframes.append(new_key)
        self.keyframes.sort(key=lambda item: item.frame)
        self.refresh_key_list()
        self.status_label.configure(text=f"已记录关键帧 {self.current_frame}")

    def delete_keyframe(self) -> None:
        selected = self.key_list.curselection()
        if selected:
            del self.keyframes[selected[0]]
        else:
            self.keyframes = [key for key in self.keyframes if key.frame != self.current_frame]
        self.refresh_key_list()
        self.crop = self.interpolated_crop(self.current_frame)
        self.render()

    def refresh_key_list(self) -> None:
        self.key_list.delete(0, "end")
        for key in self.keyframes:
            self.key_list.insert("end", f"{self.format_time(key.frame / self.fps)}   Frame {key.frame}")
        self.draw_markers()

    def select_keyframe(self, _: tk.Event) -> None:
        selected = self.key_list.curselection()
        if selected:
            self.seek(self.keyframes[selected[0]].frame)

    def draw_markers(self) -> None:
        self.marker_canvas.delete("all")
        width = max(1, self.marker_canvas.winfo_width())
        for key in self.keyframes:
            x = key.frame / max(1, self.frame_count - 1) * width
            self.marker_canvas.create_polygon(x - 5, 1, x + 5, 1, x, 12, fill="#6d8a5a", outline="")

    def click_marker(self, event: tk.Event) -> None:
        if not self.keyframes:
            return
        target = event.x / max(1, self.marker_canvas.winfo_width()) * (self.frame_count - 1)
        nearest = min(self.keyframes, key=lambda key: abs(key.frame - target))
        self.seek(nearest.frame)

    def project_payload(self) -> dict:
        return {
            "version": 1,
            "aspect": "4:3",
            "video": str(self.video_path) if self.video_path else "",
            "source_size": [self.source_w, self.source_h],
            "keyframes": [asdict(key) for key in self.keyframes],
        }

    def save_project(self) -> None:
        if not self.video_path:
            return
        default = self.video_path.with_suffix(".crop.json")
        filename = filedialog.asksaveasfilename(
            title="保存关键帧",
            initialdir=default.parent,
            initialfile=default.name,
            defaultextension=".json",
            filetypes=[("Crop project", "*.json")],
        )
        if filename:
            Path(filename).write_text(json.dumps(self.project_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
            self.status_label.configure(text="关键帧已保存")

    def load_project(self) -> None:
        filename = filedialog.askopenfilename(title="载入关键帧", filetypes=[("Crop project", "*.json")])
        if not filename:
            return
        payload = json.loads(Path(filename).read_text(encoding="utf-8"))
        video = Path(payload.get("video", ""))
        if video.exists() and video != self.video_path:
            self.open_video(video)
        self.keyframes = [Keyframe(**item) for item in payload.get("keyframes", [])]
        self.keyframes.sort(key=lambda item: item.frame)
        self.refresh_key_list()
        self.seek(self.current_frame)
        self.status_label.configure(text="关键帧已载入")

    def export_video(self) -> None:
        if not self.video_path or not self.keyframes or self.exporting:
            if not self.keyframes:
                messagebox.showinfo("需要关键帧", "请至少添加一个关键帧。")
            return
        filename = filedialog.asksaveasfilename(
            title="导出 4:3 视频",
            initialdir=self.video_path.parent,
            initialfile=f"{self.video_path.stem}-crop-4x3.mp4",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
        )
        if not filename:
            return
        self.exporting = True
        self.progress["value"] = 0
        self.status_label.configure(text="正在导出…")
        threading.Thread(target=self._export_worker, args=(Path(filename),), daemon=True).start()

    def _export_worker(self, output: Path) -> None:
        command = [
            str(FFMPEG), "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{OUTPUT_SIZE[0]}x{OUTPUT_SIZE[1]}", "-r", f"{self.fps:.8f}",
            "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ]
        cap = cv2.VideoCapture(str(self.video_path))
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            frame = 0
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                crop = self.interpolated_crop(frame)
                x1, y1, x2, y2 = self.crop_bounds(crop)
                cropped = image[int(round(y1)):int(round(y2)), int(round(x1)):int(round(x2))]
                resized = cv2.resize(cropped, OUTPUT_SIZE, interpolation=cv2.INTER_LANCZOS4)
                assert process.stdin is not None
                process.stdin.write(resized.tobytes())
                frame += 1
                if frame % 8 == 0:
                    progress = frame / self.frame_count * 100
                    self.root.after(0, lambda value=progress: self.progress.configure(value=value))
            assert process.stdin is not None
            process.stdin.close()
            return_code = process.wait()
            if return_code != 0:
                assert process.stderr is not None
                raise RuntimeError(process.stderr.read().decode("utf-8", errors="replace")[-1500:])
        except Exception as error:
            self.root.after(0, lambda: messagebox.showerror("导出失败", str(error)))
            self.root.after(0, lambda: self.status_label.configure(text="导出失败"))
        else:
            self.root.after(0, lambda: self.progress.configure(value=100))
            self.root.after(0, lambda: self.status_label.configure(text=f"已导出：{output.name}"))
            self.root.after(0, lambda: messagebox.showinfo("导出完成", f"视频已保存：\n{output}"))
        finally:
            cap.release()
            if process and process.poll() is None:
                process.kill()
            self.exporting = False


def main() -> None:
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    CropperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
