@echo off
echo Building vt.exe with PyInstaller...
pyinstaller --noconfirm --onefile --windowed --name vt --add-data "settings.json;." vt_transcriber.py
echo Build complete! The executable can be found in the "dist" folder.
pause