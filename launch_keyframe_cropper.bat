@echo off
cd /d "%~dp0"
"C:\Users\work\anaconda3\envs\emg2pose\python.exe" "scripts\keyframe_cropper.py"
if errorlevel 1 pause
