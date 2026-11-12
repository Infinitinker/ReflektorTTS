@echo off
rem Starts the ReflektorTTS desktop app from this checkout, with its overlay builds and the
rem settings window (in the 64-bit build), without a console window. For development: set up
rem .venv and build the native code first (see docs\development.md).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo No .venv here: set it up first, as docs\development.md describes.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m reflektortts.desktop --overlay native\build\bin --overlay native\build64\bin
