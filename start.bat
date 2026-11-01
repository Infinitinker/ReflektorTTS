@echo off
rem Starts the ReflektorTTS desktop app from this checkout, with its overlay builds, without a
rem console window. For development: set up .venv and build the
rem overlay first (see README.md).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo No .venv here: set it up first, as README.md describes.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m reflektortts.desktop --overlay overlay\build\bin --overlay overlay\build64\bin
