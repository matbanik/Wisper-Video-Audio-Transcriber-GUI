# Wisper-Video-Audio-Transcriber-GUI

A GUI application built with Python's Tkinter for batch transcribing audio and video files into timestamp-free PDF documents. It acts as a user-friendly front-end for the `faster-whisper-xxl.exe` command-line tool.

## Description

The application provides a complete interface to manage a transcription workflow:

- **File Queue**: Add folders to recursively find and queue all supported audio/video files. The queue can be reordered (Move Up/Down) or pruned (Remove Selected). The queue state is saved automatically.
- **Model Selection**: Choose from various Whisper model sizes (`tiny`, `small`, `medium`, `large`, `turbo`) to balance speed and accuracy.
- **Destination Folder**: Specify where the final PDF transcripts will be saved.
- **Process Control**: Start, stop, pause, and resume the entire transcription queue. The application processes files from the **bottom of the queue to the top**.
- **Output**: The tool generates a clean PDF transcript for each file, automatically stripping out timestamps. The final PDF is named using the source file's parent folder and its original filename (`parent-folder_original-filename.pdf`).
- **Console**: A log provides real-time feedback on the transcription process, errors, and application status.

!(./VT.jpg)

---

## Dependencies & Setup

The application has one critical external dependency and one Python library dependency.

### 1. `faster-whisper-xxl.exe` (Required)

This is the core transcription engine. The application will not function without it.

**Instructions:**

1.  Navigate to the `faster-whisper` releases page on GitHub: [https://github.com/guillaumekln/faster-whisper/releases](https://github.com/guillaumekln/faster-whisper/releases)
2.  Find a release (latest is recommended) and expand the "Assets" section.
3.  Download the `faster-whisper-xxl.exe` file.
4.  **Add to PATH**: For the application to find the executable, the folder containing `faster-whisper-xxl.exe` **must** be added to your Windows PATH environment variable.
    -   Create a folder, for example `C:\\ProgramFiles\\whisper\\`.
    -   Place the downloaded `faster-whisper-xxl.exe` inside it.
    -   Press the Windows key and search for "Edit the system environment variables" and open it.
    -   Click the "Environment Variables..." button.
    -   Under "System variables", find and select the `Path` variable, then click "Edit...".
    -   Click "New" and paste the path to your folder (e.g., `C:\\ProgramFiles\\whisper\\`).
    -   Click OK on all windows to save.
    -   Restart any open command prompts or the application itself for the changes to take effect.

### 2. `fpdf` (Python Library)

This library is used for creating PDF files. The script `vt_transcriber.py` includes a check to automatically install it via `pip` if it's not found when you run the script for the first time.

---

## File Descriptions

-   **`vt_transcriber.py`**: The main Python script that runs the application.
-   **`settings.json`**: This file is created automatically on the first run. It stores your selected model, destination folder, and the current file queue, allowing you to close the app and resume later.
-   [cite_start]**`build.bat`**: A batch script to package the application into a single standalone `.exe` file using PyInstaller. [cite: 1] [cite_start]The resulting executable will be in a `dist` folder. [cite: 2]
-   **`VT.jpg`**: The screenshot of the application's UI.

---

## Usage

1.  **Setup**: Ensure `faster-whisper-xxl.exe` is downloaded and its location is added to your system PATH as described above.
2.  **Run the script**: Execute `python vt_transcriber.py` from your terminal.
3.  **Configure Settings**:
    -   Select a Whisper Model. `turbo` is the default.
    -   Select a Destination Folder for your PDF outputs.
4.  **Build Queue**:
    -   Click "Find Files" and select a folder containing your media files. The app will scan it and add all valid files to the queue.
    -   Use "Move Up", "Move Down", or "Remove Selected" to manage the queue.
5.  **Start**: Click "Start Transcription". The application will begin processing files from the bottom of the list upwards.

