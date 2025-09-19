@echo off
echo Building the executable...

rem Specify the name of your Python script
set SCRIPT_NAME=pdf_merger_app.py

rem Specify the desired executable name
set EXE_NAME=pm.exe

rem Run PyInstaller
pyinstaller --noconfirm --onefile --windowed --name %EXE_NAME% %SCRIPT_NAME%

echo.
echo Build process finished.
echo Your executable should be in the "dist" folder.
echo.
pause