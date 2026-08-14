# 4:3 Keyframe Video Cropper

Double-click `launch_keyframe_cropper.bat` in the project root.

## Workflow

1. Move the timeline to the first position that needs framing.
2. Drag inside the crop box to move it.
3. Drag a corner or use the mouse wheel to resize it. The ratio stays at 4:3.
4. Click `添加 / 更新关键帧` or press Space.
5. Repeat at other points in the video. The camera path is smoothly interpolated.
6. Save the keyframes as JSON when needed.
7. Click `导出 4:3 视频` to create a 960 x 720 H.264 MP4.

Keyboard controls:

- Left / Right: move one frame.
- Shift + Left / Right: move ten frames.
- Space: add or update a keyframe.
- Ctrl + S: save keyframes.
