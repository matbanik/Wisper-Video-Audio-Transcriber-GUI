import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import json
import subprocess
import threading
from datetime import datetime
from fpdf import FPDF
import sys
import time
import re # Import the regular expression module

# Constants
SETTINGS_FILE = 'settings.json'
SUPPORTED_EXTENSIONS = (
    '.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', # Video
    '.mp3', '.wav', '.aac', '.flac', '.ogg' # Audio
)

class VideoTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Transcriber")
        self.root.geometry("1000x700") # Set initial window size
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle window close event

        self.model_options = ["tiny", "small", "medium", "large", "turbo"]
        self.default_model = "turbo"
        self.current_destination_folder = self.get_downloads_folder()

        self.transcription_thread = None
        self.stop_flag = threading.Event()
        self.pause_flag = threading.Event()

        self.setup_ui()
        self.load_settings()
        self.check_whisper_exe()

    def setup_ui(self):
        # --- Top Frame (Settings) ---
        top_frame = ttk.LabelFrame(self.root, text="Settings", padding="10")
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # Model Selection
        model_frame = ttk.Frame(top_frame)
        model_frame.pack(fill=tk.X, pady=5)
        ttk.Label(model_frame, text="Whisper Model:").pack(side=tk.LEFT, padx=(0, 5))
        self.model_var = tk.StringVar(self.root)
        self.model_var.set(self.default_model)
        self.model_dropdown = ttk.Combobox(model_frame, textvariable=self.model_var,
                                           values=self.model_options, state="readonly", width=15)
        self.model_dropdown.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Destination Folder
        dest_frame = ttk.Frame(top_frame)
        dest_frame.pack(fill=tk.X, pady=5)
        ttk.Label(dest_frame, text="Destination Folder:").pack(side=tk.LEFT, padx=(0, 5))
        self.dest_folder_entry = ttk.Entry(dest_frame, state="readonly", width=50)
        self.dest_folder_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.update_dest_folder_entry() # Set initial value
        ttk.Button(dest_frame, text="Select", command=self.select_destination_folder).pack(side=tk.LEFT)

        # --- Middle Frame (File List and Controls) ---
        middle_frame = ttk.LabelFrame(self.root, text="Transcription Queue", padding="10")
        middle_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Treeview (File List)
        self.tree = ttk.Treeview(middle_frame, columns=("Processed", "Path", "Filename"), show="headings")
        self.tree.heading("Processed", text="Processed", anchor=tk.W)
        self.tree.heading("Path", text="File Path", anchor=tk.W)
        self.tree.heading("Filename", text="Filename", anchor=tk.W)

        # Adjust column widths
        self.tree.column("Processed", width=80, minwidth=60, stretch=tk.NO)
        self.tree.column("Path", width=400, minwidth=200)
        self.tree.column("Filename", width=250, minwidth=150)

        self.tree_scroll_y = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree_scroll_x = ttk.Scrollbar(middle_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set, xscrollcommand=self.tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_x.grid(row=1, column=0, sticky="ew")

        middle_frame.grid_rowconfigure(0, weight=1)
        middle_frame.grid_columnconfigure(0, weight=1)

        # File Management Buttons
        file_buttons_frame = ttk.Frame(middle_frame)
        file_buttons_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")
        ttk.Button(file_buttons_frame, text="Find Files", command=self.find_source_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="Move Up", command=lambda: self.move_item("up")).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="Move Down", command=lambda: self.move_item("down")).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_buttons_frame, text="Remove Selected", command=self.remove_selected_files).pack(side=tk.LEFT, padx=5)

        # Transcription Control Buttons
        control_buttons_frame = ttk.Frame(middle_frame)
        control_buttons_frame.grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")
        self.start_button = ttk.Button(control_buttons_frame, text="Start Transcription", command=self.start_transcription)
        self.start_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_buttons_frame, text="Stop Transcription", command=self.stop_transcription, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.pause_button = ttk.Button(control_buttons_frame, text="Pause", command=self.pause_transcription, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        self.resume_button = ttk.Button(control_buttons_frame, text="Resume", command=self.resume_transcription, state=tk.DISABLED)
        self.resume_button.pack(side=tk.LEFT, padx=5)


        # --- Bottom Frame (Console) ---
        bottom_frame = ttk.LabelFrame(self.root, text="Console Output", padding="10")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.console_text = tk.Text(bottom_frame, wrap=tk.WORD, state="disabled", height=10, bg="#f0f0f0")
        self.console_text.pack(fill=tk.BOTH, expand=True)

        self.console_scroll = ttk.Scrollbar(bottom_frame, command=self.console_text.yview)
        self.console_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_text.config(yscrollcommand=self.console_scroll.set)

    def update_dest_folder_entry(self):
        self.dest_folder_entry.config(state="normal")
        self.dest_folder_entry.delete(0, tk.END)
        self.dest_folder_entry.insert(0, self.current_destination_folder)
        self.dest_folder_entry.config(state="readonly")

    def check_whisper_exe(self):
        """Checks if faster-whisper-xxl.exe is available in the system's PATH."""
        try:
            subprocess.run(["faster-whisper-xxl.exe", "--version"], check=True,
                           capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.update_console("[INFO] 'faster-whisper-xxl.exe' found in PATH.", "green")
            self.whisper_exe_found = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.update_console("[ERROR] 'faster-whisper-xxl.exe' not found in PATH or not executable. "
                                 "Please ensure it's installed and added to your system's PATH.", "red")
            self.whisper_exe_found = False
            # Disable start button if executable is not found
            self.start_button.config(state=tk.DISABLED)


    def get_downloads_folder(self):
        """Returns the path to the user's Downloads folder."""
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            CSIDL_DOWNLOADS = 40960 # Downloads folder (Vista onwards)

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DOWNLOADS, None, 0, buf)
            return buf.value
        else: # For Linux/macOS, a common fallback
            return os.path.join(os.path.expanduser("~"), "Downloads")

    def update_console(self, message, color="black"):
        """Appends a message to the console text widget."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.config(state="normal")
        self.console_text.insert(tk.END, f"[{timestamp}] {message}\n", color)
        self.console_text.see(tk.END) # Scroll to the end
        self.console_text.config(state="disabled")

        self.console_text.tag_config("red", foreground="red")
        self.console_text.tag_config("green", foreground="green")
        self.console_text.tag_config("blue", foreground="blue")
        self.console_text.tag_config("orange", foreground="orange")


    def load_settings(self):
        """Loads settings from settings.json."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.model_var.set(settings.get('model', self.default_model))
                    self.current_destination_folder = settings.get('destination_folder', self.get_downloads_folder())
                    self.update_dest_folder_entry()
                    self.populate_treeview(settings.get('file_queue', []))
                    self.update_console("[INFO] Settings loaded successfully.")
            except json.JSONDecodeError:
                self.update_console("[WARNING] Could not decode settings.json. Starting with default settings.", "orange")
            except Exception as e:
                self.update_console(f"[ERROR] Error loading settings: {e}", "red")
        else:
            self.update_console("[INFO] settings.json not found. Starting with default settings.")


    def save_settings(self):
        """Saves current settings to settings.json."""
        settings = {
            'model': self.model_var.get(),
            'destination_folder': self.current_destination_folder,
            'file_queue': self.get_current_queue_data()
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            self.update_console("[INFO] Settings saved successfully.")
        except Exception as e:
            self.update_console(f"[ERROR] Error saving settings: {e}", "red")

    def on_closing(self):
        """Called when the window is closed."""
        if self.transcription_thread and self.transcription_thread.is_alive():
            if messagebox.askyesno("Confirm Exit", "A transcription is in progress. Do you want to stop it and exit?"):
                self.stop_transcription()
                self.transcription_thread.join(timeout=5) # Give it a moment to stop
                self.save_settings()
                self.root.destroy()
            else:
                pass # Don't destroy if user cancels
        else:
            self.save_settings()
            self.root.destroy()

    def get_current_queue_data(self):
        """Extracts current data from the Treeview for saving."""
        queue_data = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            queue_data.append({
                'processed': values[0],
                'path': values[1],
                'filename': values[2]
            })
        return queue_data

    def populate_treeview(self, file_queue_data):
        """Populates the Treeview from loaded settings."""
        self.tree.delete(*self.tree.get_children()) # Clear existing items
        for item in file_queue_data:
            self.tree.insert("", "end", values=(item['processed'], item['path'], item['filename']))

    def find_source_folder(self):
        """Opens a directory dialog, scans for video/audio files, and adds them to the list."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.update_console(f"[INFO] Scanning folder: {folder_selected}")
            found_files = []
            for root_dir, _, files in os.walk(folder_selected):
                for file in files:
                    if os.path.splitext(file)[1].lower() in SUPPORTED_EXTENSIONS:
                        full_path = os.path.join(root_dir, file)
                        found_files.append((full_path, file))
            self.add_files_to_list(found_files)
            self.update_console(f"[INFO] Found {len(found_files)} new files in {folder_selected}.")

    def add_files_to_list(self, file_paths_and_names):
        """Adds new files to the Treeview, avoiding duplicates based on full path."""
        existing_paths = {self.tree.item(item, 'values')[1] for item in self.tree.get_children()}
        added_count = 0
        for full_path, filename in file_paths_and_names:
            if full_path not in existing_paths:
                self.tree.insert("", "end", values=("No", full_path, filename))
                added_count += 1
        self.update_console(f"[INFO] Added {added_count} new files to the queue.")


    def select_destination_folder(self):
        """Opens a directory dialog for selecting the output destination."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.current_destination_folder = folder_selected
            self.update_dest_folder_entry()
            self.update_console(f"[INFO] Destination folder set to: {self.current_destination_folder}")

    def update_file_status(self, item_id, processed_status):
        """Updates the 'Processed' status for a given item in the Treeview."""
        current_values = list(self.tree.item(item_id, 'values'))
        current_values[0] = processed_status # Update the first column
        self.tree.item(item_id, values=current_values)

    def move_item(self, direction):
        """Moves selected item up or down in the Treeview."""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        for item_id in selected_items:
            current_index = self.tree.index(item_id)
            if direction == "up":
                if current_index > 0:
                    self.tree.move(item_id, "", current_index - 1)
            elif direction == "down":
                if current_index < len(self.tree.get_children()) - 1:
                    self.tree.move(item_id, "", current_index + 1)
        self.save_settings() # Save order changes

    def remove_selected_files(self):
        """Removes selected files from the Treeview."""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove {len(selected_items)} selected file(s) from the queue?"):
            for item_id in selected_items:
                self.tree.delete(item_id)
            self.save_settings()
            self.update_console(f"[INFO] Removed {len(selected_items)} file(s) from the queue.")


    def start_transcription(self):
        """Starts the transcription process in a new thread."""
        if not self.whisper_exe_found:
            self.update_console("[ERROR] Cannot start. 'faster-whisper-xxl.exe' not found.", "red")
            return

        if self.transcription_thread and self.transcription_thread.is_alive():
            self.update_console("[WARNING] Transcription is already running.", "orange")
            return

        self.stop_flag.clear() # Clear stop flag for new run
        self.pause_flag.clear() # Clear pause flag
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.NORMAL)
        self.resume_button.config(state=tk.DISABLED)
        self.update_console("[INFO] Transcription process started.", "blue")

        self.transcription_thread = threading.Thread(target=self.transcription_worker)
        self.transcription_thread.daemon = True # Allow main program to exit even if thread is running
        self.transcription_thread.start()

    def stop_transcription(self):
        """Sets the stop flag to terminate the transcription thread."""
        self.stop_flag.set()
        self.update_console("[INFO] Stop requested. Waiting for current transcription to finish...", "blue")
        self.set_control_buttons_state(stopped=True)

    def pause_transcription(self):
        """Sets the pause flag to pause the transcription thread."""
        self.pause_flag.set()
        self.update_console("[INFO] Transcription paused.", "blue")
        self.set_control_buttons_state(paused=True)

    def resume_transcription(self):
        """Clears the pause flag to resume the transcription thread."""
        self.pause_flag.clear()
        self.update_console("[INFO] Transcription resumed.", "blue")
        self.set_control_buttons_state(resumed=True)

    def set_control_buttons_state(self, stopped=False, paused=False, resumed=False):
        """Helper to manage button states."""
        if stopped:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.DISABLED)
        elif paused:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.NORMAL)
        elif resumed:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.NORMAL)
            self.resume_button.config(state=tk.DISABLED)
        else: # Initial state when started
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.NORMAL)
            self.resume_button.config(state=tk.DISABLED)


    def transcription_worker(self):
        """Worker function for transcription, run in a separate thread."""
        model = self.model_var.get()
        destination_folder = self.current_destination_folder

        # Get items in reverse order (descending) as per request
        all_item_ids = list(self.tree.get_children())
        all_item_ids.reverse()

        for item_id in all_item_ids:
            if self.stop_flag.is_set():
                self.update_console("[INFO] Transcription stopped by user.", "blue")
                break

            while self.pause_flag.is_set():
                self.update_console("[INFO] Transcription paused. Waiting to resume...", "blue")
                time.sleep(1) # Wait for 1 second before checking pause_flag again
                if self.stop_flag.is_set(): # Allow stopping even while paused
                    self.update_console("[INFO] Transcription stopped while paused.", "blue")
                    break

            if self.stop_flag.is_set(): # Re-check after pause loop
                break

            values = self.tree.item(item_id, 'values')
            processed_status = values[0]
            file_path = values[1]
            filename = values[2]

            # Construct output file names based on original file for TXT
            base_filename = os.path.splitext(filename)[0]
            output_txt_filename_whisper = f"{base_filename}.txt" # faster-whisper-xxl.exe output filename
            txt_output_path = os.path.join(destination_folder, output_txt_filename_whisper)

            # Construct PDF filename with prepended folder name
            parent_folder_name = os.path.basename(os.path.dirname(file_path))
            if not parent_folder_name: # Fallback if file is directly in root
                parent_folder_name = "Transcribed"
            output_pdf_filename = f"{parent_folder_name}_{base_filename}.pdf"
            pdf_output_path = os.path.join(destination_folder, output_pdf_filename)


            # --- Check if already processed or can be retried ---
            if processed_status == "Yes":
                self.update_console(f"[INFO] Skipping '{filename}' - already processed.", "blue")
                continue

            # If failed, but TXT exists and is not empty, attempt PDF conversion directly
            if processed_status == "Failed" and os.path.exists(txt_output_path) and os.path.getsize(txt_output_path) > 0:
                self.update_console(f"[INFO] Detected existing TXT for failed '{filename}'. Attempting PDF conversion.", "blue")
                # Update UI status immediately before conversion attempt
                self.root.after(0, self.update_file_status, item_id, "Retrying PDF...")
                try:
                    self.convert_txt_to_pdf(txt_output_path, pdf_output_path)
                    self.root.after(0, self.update_file_status, item_id, "Yes")
                    self.root.after(0, self.save_settings)
                    self.update_console(f"[SUCCESS] Retried PDF conversion for '{output_txt_filename_whisper}' to PDF: '{output_pdf_filename}'", "green")
                except Exception as e:
                    self.update_console(f"[ERROR] Failed to retry PDF conversion for '{filename}': {e}", "red")
                    self.root.after(0, self.update_file_status, item_id, "Failed")
                continue # Move to next file regardless of PDF retry success/failure


            # Check if PDF already exists (even if 'Processed' status is 'No' due to manual deletion)
            if os.path.exists(pdf_output_path):
                self.update_console(f"[INFO] PDF for '{filename}' already exists. Marking as processed.", "blue")
                self.root.after(0, self.update_file_status, item_id, "Yes")
                self.root.after(0, self.save_settings)
                continue

            self.update_console(f"[INFO] Transcribing '{filename}' using '{model}' model...", "blue")
            self.root.after(0, self.update_file_status, item_id, "Processing...") # Update GUI immediately

            try:
                # Command to run faster-whisper-xxl.exe
                # Note: --output_dir is where the .txt file will be saved.
                command = [
                    "faster-whisper-xxl.exe",
                    file_path,
                    "--model", model,
                    "--output_dir", destination_folder,
                    "--output_format", "txt", # Ensure text output for PDF conversion
                    "--compute_type", "float32", # Forcing float32 for maximum compatibility
                    "--vad_filter", "true",
                    "--task", "transcribe",
                    "--word_timestamps", "false", # Disable word timestamps
                    "--beep_off",
                ]
                self.update_console(f"[DEBUG] Executing: {' '.join(command)}")

                # Use creationflags for Windows to prevent console window from popping up
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, bufsize=1, universal_newlines=True,
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

                # Monitor process output in real-time
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        self.root.after(0, self.update_console, output.strip(), "blue")
                    if self.stop_flag.is_set():
                        # If stop requested, terminate the subprocess
                        process.terminate()
                        self.update_console(f"[INFO] Terminated transcription for '{filename}'.", "orange")
                        break # Break out of inner while loop

                process.wait() # Wait for the process to truly finish/terminate

                if process.returncode == 0:
                    self.update_console(f"[SUCCESS] Transcription of '{filename}' completed.", "green")
                    # Ensure the TXT file is in the expected place before conversion
                    if os.path.exists(txt_output_path) and os.path.getsize(txt_output_path) > 0:
                        self.convert_txt_to_pdf(txt_output_path, pdf_output_path)
                        self.root.after(0, self.update_file_status, item_id, "Yes") # Update GUI
                        self.root.after(0, self.save_settings)
                        self.update_console(f"[SUCCESS] Converted '{output_txt_filename_whisper}' to PDF: '{output_pdf_filename}'", "green")
                    else:
                        self.update_console(f"[ERROR] Expected TXT file '{txt_output_path}' not found or is empty after successful transcription process. (Check faster-whisper-xxl.exe output)", "red")
                        self.root.after(0, self.update_file_status, item_id, "Failed")
                else:
                    stderr_output = process.stderr.read()
                    self.update_console(f"[ERROR] Transcription of '{filename}' failed. Exit Code: {process.returncode}", "red")
                    if stderr_output:
                        self.update_console(f"[ERROR] Subprocess Error: {stderr_output.strip()}", "red")

                    # Special handling for Exit Code 3221226505
                    if process.returncode == 3221226505 and os.path.exists(txt_output_path) and os.path.getsize(txt_output_path) > 0:
                        self.update_console(f"[INFO] Despite Exit Code {process.returncode}, TXT file exists. Attempting PDF conversion for '{filename}'.", "orange")
                        try:
                            self.convert_txt_to_pdf(txt_output_path, pdf_output_path)
                            self.root.after(0, self.update_file_status, item_id, "Yes")
                            self.root.after(0, self.save_settings)
                            self.update_console(f"[SUCCESS] PDF conversion successful despite transcription exit code for '{filename}'.", "green")
                        except Exception as pdf_e:
                            self.update_console(f"[ERROR] PDF conversion failed even after transcription error: {pdf_e}", "red")
                            self.root.after(0, self.update_file_status, item_id, "Failed")
                    else:
                        self.root.after(0, self.update_file_status, item_id, "Failed")

            except FileNotFoundError:
                self.update_console(f"[ERROR] 'faster-whisper-xxl.exe' not found. "
                                     f"Please ensure it's in your system PATH.", "red")
                self.root.after(0, self.update_file_status, item_id, "Failed")
                self.stop_flag.set() # Stop the entire process
                break
            except Exception as e:
                self.update_console(f"[ERROR] An unexpected error occurred during transcription for '{filename}': {e}", "red")
                self.root.after(0, self.update_file_status, item_id, "Failed")
                # Continue to next file or stop, depending on desired behavior
                # For now, let's continue to the next file but mark current as failed.

        self.update_console("[INFO] Transcription queue finished or stopped.", "blue")
        self.root.after(0, self.set_control_buttons_state, True) # Reset buttons

    def convert_txt_to_pdf(self, txt_path, pdf_path):
        """Converts a text file to a PDF file and removes timestamps."""
        if not os.path.exists(txt_path) or os.path.getsize(txt_path) == 0:
            self.update_console(f"[ERROR] Text file not found or is empty for PDF conversion: {txt_path}", "red")
            raise FileNotFoundError(f"Text file not found or empty: {txt_path}") # Raise for handling in worker

        # Regex to find timestamps like [00:01.500 --> 00:04.320] or [01:00:01.500 --> 01:00:04.320]
        timestamp_pattern = re.compile(r'\[(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\]\s*')

        try:
            pdf = FPDF()
            # Set top, right, left, and bottom margins
            pdf.set_margins(15, 15, 15)
            pdf.add_page()
            pdf.set_font("Arial", size=12)

            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Remove timestamps from the line
                    cleaned_line = timestamp_pattern.sub('', line).strip()

                    # Only write if there's actual content after removing timestamps
                    if cleaned_line:
                        # FPDF requires strings, ensure proper encoding and handling of special chars
                        try:
                            # Add a newline character back after stripping and cleaning
                            pdf.write(8, cleaned_line.encode('latin-1', 'replace').decode('latin-1') + "\n")
                        except UnicodeEncodeError:
                            self.update_console(f"[WARNING] Encoding issue with line in {txt_path}. Skipping problematic characters.", "orange")
                            # Fallback for complex characters - replace with ? or similar
                            pdf.write(8, cleaned_line.encode('ascii', 'replace').decode('ascii') + "\n")
            pdf.output(pdf_path)
            # Optionally delete the source .txt file after successful PDF conversion
            # os.remove(txt_path)
            self.update_console(f"[INFO] '{os.path.basename(txt_path)}' converted to PDF.", "green")
        except Exception as e:
            self.update_console(f"[ERROR] Failed to convert '{txt_path}' to PDF: {e}", "red")
            raise # Re-raise to be caught in the worker thread


if __name__ == "__main__":
    # Ensure fpdf is installed
    try:
        from fpdf import FPDF
    except ImportError:
        print("FPDF library not found. Installing now...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf"])
            from fpdf import FPDF
            print("FPDF installed successfully.")
        except Exception as e:
            print(f"Failed to install FPDF. Please install manually: pip install fpdf. Error: {e}")
            sys.exit(1)

    root = tk.Tk()
    app = VideoTranscriberApp(root)
    root.mainloop()
