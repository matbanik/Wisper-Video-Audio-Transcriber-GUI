import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os
import json
import threading
import time
import fitz  # PyMuPDF
import re
import tempfile

# --- Constants and Global Variables ---
SETTINGS_FILE = "settings.json"
DEFAULT_OUTPUT_FILENAME = "MergedPDFs.pdf"
# Determine the user's Downloads directory across different OS
DOWNLOADS_PATH = os.path.join(os.path.expanduser("~"), "Downloads")

# Global variables for controlling the merge process thread
merge_thread = None
merge_stop_event = threading.Event()
merge_pause_event = threading.Event()
merge_running = False
merge_paused = False

class PDFMergerApp:
    def __init__(self, master):
        self.master = master
        master.title("PDF Pure Text Merger & PII Scrubber")
        master.geometry("800x850") # Increased height for new section

        self.pdf_files = [] # List to store full paths of PDF files
        self.output_folder = DOWNLOADS_PATH # Default output folder
        self.total_word_count = 0 # Accumulator for total words

        # --- Configuration Variables ---
        self.remove_timestamps_var = tk.BooleanVar(value=False)
        self.remove_images_var = tk.BooleanVar(value=False)
        self.remove_pii_var = tk.BooleanVar(value=False)
        self.custom_pii_var = tk.StringVar(value="") 
        # New: Variables for splitting output
        self.split_by_words_var = tk.BooleanVar(value=False)
        self.split_word_count_var = tk.StringVar(value="10000")

        # Initialize widgets first so console_output exists before load_settings
        self.create_widgets() # Build the GUI elements
        self.load_settings() # Load saved settings on startup
        self.update_word_count_display() # Update the word count label initially
        self._update_pii_field_visibility() # Set initial state of custom PII field
        self._update_split_field_visibility() # Set initial state of split field

    def create_widgets(self):
        """Creates and lays out all the GUI widgets."""
        # --- Top Section: Word Count and Destination ---
        top_frame = tk.Frame(self.master, bd=2, relief="groove", padx=10, pady=10)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.total_words_label = tk.Label(top_frame, text=f"Total Words: {self.total_word_count}", font=("Arial", 14, "bold"))
        self.total_words_label.pack(side=tk.TOP, pady=5)

        dest_frame = tk.Frame(top_frame)
        dest_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        tk.Label(dest_frame, text="Output Folder:").pack(side=tk.LEFT)
        self.output_folder_label = tk.Label(dest_frame, text=self.output_folder, bg="lightgray", width=50, anchor="w", relief="sunken")
        self.output_folder_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.select_folder_btn = tk.Button(dest_frame, text="Select", command=self.select_output_folder)
        self.select_folder_btn.pack(side=tk.RIGHT)

        # --- File List Section ---
        list_frame = tk.Frame(self.master, bd=2, relief="groove", padx=10, pady=10)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(list_frame, text="PDF Files for Merger:", font=("Arial", 12)).pack(side=tk.TOP, anchor="w")

        self.pdf_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=10)
        self.pdf_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.pdf_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.pdf_listbox.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self.pdf_listbox.config(yscrollcommand=scrollbar.set)

        button_frame = tk.Frame(list_frame)
        button_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_btn = tk.Button(button_frame, text="Add PDF", command=self.add_pdf_file)
        self.add_btn.pack(pady=5, fill=tk.X)
        self.move_up_btn = tk.Button(button_frame, text="Move Up", command=self.move_pdf_up, state=tk.DISABLED)
        self.move_up_btn.pack(pady=5, fill=tk.X)
        self.move_down_btn = tk.Button(button_frame, text="Move Down", command=self.move_pdf_down, state=tk.DISABLED)
        self.move_down_btn.pack(pady=5, fill=tk.X)
        self.remove_btn = tk.Button(button_frame, text="Remove", command=self.remove_pdf_file, state=tk.DISABLED)
        self.remove_btn.pack(pady=5, fill=tk.X)
        self.clear_all_btn = tk.Button(button_frame, text="Clear All", command=self.clear_all_pdfs, state=tk.DISABLED)
        self.clear_all_btn.pack(pady=5, fill=tk.X)

        # --- Configuration Section ---
        config_frame = tk.LabelFrame(self.master, text="Configuration", bd=2, relief="groove", padx=10, pady=10)
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.remove_timestamps_checkbox = tk.Checkbutton(config_frame, text="Remove Timestamps", variable=self.remove_timestamps_var, command=lambda: self.log_and_save_setting("Timestamps", self.remove_timestamps_var))
        self.remove_timestamps_checkbox.pack(anchor="w", padx=5, pady=2)

        self.remove_images_checkbox = tk.Checkbutton(config_frame, text="Remove Images (extract text only)", variable=self.remove_images_var, command=lambda: self.log_and_save_setting("Images", self.remove_images_var))
        self.remove_images_checkbox.pack(anchor="w", padx=5, pady=2)
        
        self.remove_pii_checkbox = tk.Checkbutton(config_frame, text="Remove PII (Names, Addresses, etc.)", variable=self.remove_pii_var, command=self.on_pii_checkbox_change)
        self.remove_pii_checkbox.pack(anchor="w", padx=5, pady=2)

        self.custom_pii_label = tk.Label(config_frame, text="Custom Strings to Remove (comma-separated):")
        self.custom_pii_label.pack(anchor="w", padx=25, pady=(5,0))
        self.custom_pii_entry = tk.Entry(config_frame, textvariable=self.custom_pii_var)
        self.custom_pii_entry.pack(fill=tk.X, padx=25, pady=2)
        self.custom_pii_var.trace_add("write", lambda *args: self.save_settings())
        
        # New: Split by words widgets
        self.split_by_words_checkbox = tk.Checkbutton(config_frame, text="Split output by words", variable=self.split_by_words_var, command=self.on_split_checkbox_change)
        self.split_by_words_checkbox.pack(anchor="w", padx=5, pady=(10,2))
        
        self.split_word_count_label = tk.Label(config_frame, text="Number of words per file:")
        self.split_word_count_label.pack(anchor="w", padx=25, pady=(5,0))
        self.split_word_count_entry = tk.Entry(config_frame, textvariable=self.split_word_count_var)
        self.split_word_count_entry.pack(fill=tk.X, padx=25, pady=2)
        self.split_word_count_var.trace_add("write", lambda *args: self.save_settings())


        # --- Control Buttons Section ---
        control_frame = tk.Frame(self.master, bd=2, relief="groove", padx=10, pady=10)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.start_btn = tk.Button(control_frame, text="Start Merge", command=self.start_merge, width=15)
        self.start_btn.pack(side=tk.LEFT, expand=True, padx=5, pady=5)
        self.pause_btn = tk.Button(control_frame, text="Pause", command=self.pause_merge, width=15, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, expand=True, padx=5, pady=5)
        self.stop_btn = tk.Button(control_frame, text="Stop", command=self.stop_merge, width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, expand=True, padx=5, pady=5)

        # --- Console Output Section ---
        console_frame = tk.Frame(self.master, bd=2, relief="groove", padx=10, pady=10)
        console_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(console_frame, text="Console Output:", font=("Arial", 12)).pack(side=tk.TOP, anchor="w")
        self.console_output = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD, height=10, bg="black", fg="lime", font=("Consolas", 10))
        self.console_output.pack(fill=tk.BOTH, expand=True)
        self.console_output.tag_config("info", foreground="white")
        self.console_output.tag_config("error", foreground="red")
        self.console_output.tag_config("progress", foreground="cyan")
        self.console_output.tag_config("success", foreground="green")
        self.console_output.tag_config("warning", foreground="yellow")

        self.print_to_console("Welcome to PDF Merger & PII Scrubber!", "info")
        self.print_to_console("Select PDF files and click 'Start Merge'.", "info")
        self.print_to_console(f"Default output folder: {self.output_folder}", "info")
        
    def on_pii_checkbox_change(self):
        """Handles changes to the PII checkbox state."""
        self.log_and_save_setting("PII", self.remove_pii_var)
        self._update_pii_field_visibility()

    def _update_pii_field_visibility(self):
        """Enables or disables the custom PII field based on the checkbox."""
        state = tk.NORMAL if self.remove_pii_var.get() else tk.DISABLED
        self.custom_pii_label.config(state=state)
        self.custom_pii_entry.config(state=state)

    # New: Method to handle split checkbox changes
    def on_split_checkbox_change(self):
        """Handles changes to the 'Split by words' checkbox state."""
        self.log_and_save_setting("Split by Words", self.split_by_words_var)
        self._update_split_field_visibility()

    # New: Method to enable/disable split word count field
    def _update_split_field_visibility(self):
        """Enables or disables the split word count field based on the checkbox."""
        state = tk.NORMAL if self.split_by_words_var.get() else tk.DISABLED
        self.split_word_count_label.config(state=state)
        self.split_word_count_entry.config(state=state)

    def on_listbox_select(self, event):
        """Enables/disables buttons based on listbox selection."""
        if self.pdf_listbox.curselection():
            self.move_up_btn.config(state=tk.NORMAL)
            self.move_down_btn.config(state=tk.NORMAL)
            self.remove_btn.config(state=tk.NORMAL)
        else:
            self.move_up_btn.config(state=tk.DISABLED)
            self.move_down_btn.config(state=tk.DISABLED)
            self.remove_btn.config(state=tk.DISABLED)
        
        self.clear_all_btn.config(state=tk.NORMAL if self.pdf_listbox.size() > 0 else tk.DISABLED)

    def print_to_console(self, message, tag=None):
        """Prints a message to the console output widget."""
        self.console_output.insert(tk.END, message + "\n", tag)
        self.console_output.see(tk.END)

    def log_and_save_setting(self, setting_name, var):
        """Logs checkbox state changes and saves all settings."""
        state = "Enabled" if var.get() else "Disabled"
        self.print_to_console(f"Configuration: {setting_name} {state}.", "info")
        self.save_settings()

    def load_settings(self):
        """Loads settings from settings.json."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
                    self.pdf_files = settings.get("pdf_files", [])
                    self.output_folder = settings.get("output_folder", DOWNLOADS_PATH)
                    self.remove_timestamps_var.set(settings.get("remove_timestamps_enabled", False))
                    self.remove_images_var.set(settings.get("remove_images_enabled", False))
                    self.remove_pii_var.set(settings.get("remove_pii_enabled", False))
                    self.custom_pii_var.set(settings.get("custom_pii_strings", "")) 
                    # New: Load split settings
                    self.split_by_words_var.set(settings.get("split_by_words_enabled", False))
                    self.split_word_count_var.set(settings.get("split_word_count", "10000"))
                    
                    self.print_to_console(f"Loaded settings from {SETTINGS_FILE}", "info")
                    
                    self.total_word_count = 0
                    files_to_keep = []
                    self.pdf_listbox.delete(0, tk.END) 
                    for pdf_path in self.pdf_files:
                        if os.path.exists(pdf_path):
                            try:
                                text = self._extract_text_from_pdf(pdf_path) 
                                self.total_word_count += self._count_words(text)
                                files_to_keep.append(pdf_path)
                                self.pdf_listbox.insert(tk.END, os.path.basename(pdf_path))
                            except Exception as e:
                                self.print_to_console(f"Error processing {os.path.basename(pdf_path)} on load: {e}", "error")
                        else:
                            self.print_to_console(f"Warning: Stored file not found: {pdf_path}. Removing from list.", "warning")
                    self.pdf_files = files_to_keep
            except Exception as e:
                self.print_to_console(f"Error loading settings: {e}. Starting with defaults.", "error")
                self.pdf_files = []
                self.output_folder = DOWNLOADS_PATH
        
        self.output_folder_label.config(text=self.output_folder)
        self.on_listbox_select(None)

    def save_settings(self):
        """Saves current settings to settings.json."""
        settings = {
            "pdf_files": self.pdf_files,
            "output_folder": self.output_folder,
            "remove_timestamps_enabled": self.remove_timestamps_var.get(),
            "remove_images_enabled": self.remove_images_var.get(),
            "remove_pii_enabled": self.remove_pii_var.get(),
            "custom_pii_strings": self.custom_pii_var.get(),
            # New: Save split settings
            "split_by_words_enabled": self.split_by_words_var.get(),
            "split_word_count": self.split_word_count_var.get()
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            self.print_to_console(f"Error saving settings: {e}", "error")

    def _extract_text_from_pdf(self, pdf_path):
        """Extracts text from a PDF for word counting."""
        text = ""
        timestamp_regex = r'\[(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\]\s*'
        try:
            # Modified: Can now accept a document object or a path
            if isinstance(pdf_path, str):
                doc = fitz.open(pdf_path)
                close_doc = True
            else:
                doc = pdf_path
                close_doc = False

            for page in doc:
                page_text = page.get_text("text")
                if self.remove_timestamps_var.get():
                    page_text = re.sub(timestamp_regex, '', page_text)
                text += page_text + " "
            
            if close_doc:
                doc.close()
        except Exception as e:
            self.print_to_console(f"Error extracting text from PDF: {e}", "error")
            if 'close_doc' in locals() and close_doc and 'doc' in locals():
                doc.close()
            raise
        return text

    def _count_words(self, text):
        """Counts words in a given text string."""
        return len(re.findall(r'\b\w+\b', text.lower()))

    def update_word_count_display(self):
        """Updates the total word count label in the GUI."""
        self.total_words_label.config(text=f"Total Words: {self.total_word_count}")

    def add_pdf_file(self):
        """Adds selected PDF files to the list."""
        file_paths = filedialog.askopenfilenames(title="Select PDF Files", filetypes=[("PDF files", "*.pdf")])
        if not file_paths:
            return
            
        for file_path in file_paths:
            if file_path not in self.pdf_files:
                self.pdf_files.append(file_path)
                self.pdf_listbox.insert(tk.END, os.path.basename(file_path))
                self.print_to_console(f"Added: {os.path.basename(file_path)}", "info")
                try:
                    text = self._extract_text_from_pdf(file_path) 
                    words_in_file = self._count_words(text)
                    self.total_word_count += words_in_file
                    self.print_to_console(f"  - Words in '{os.path.basename(file_path)}': {words_in_file}", "info")
                except Exception:
                    self.print_to_console(f"Could not count words for {os.path.basename(file_path)}.", "error")
                    self.pdf_files.remove(file_path)
                    self.pdf_listbox.delete(tk.END)
            else:
                self.print_to_console(f"'{os.path.basename(file_path)}' is already in the list.", "info")
        
        self.update_word_count_display()
        self.save_settings()
        self.on_listbox_select(None)

    def remove_pdf_file(self):
        """Removes selected PDF files from the list."""
        selected_indices = sorted(self.pdf_listbox.curselection(), reverse=True)
        if not selected_indices:
            return

        for index in selected_indices:
            removed_path = self.pdf_files.pop(index)
            self.pdf_listbox.delete(index)
            self.print_to_console(f"Removed: {os.path.basename(removed_path)}", "info")
        
        self.total_word_count = 0
        for pdf_path in self.pdf_files:
            try:
                text = self._extract_text_from_pdf(pdf_path) 
                self.total_word_count += self._count_words(text)
            except Exception as e:
                self.print_to_console(f"Error recalculating words for {os.path.basename(pdf_path)}: {e}", "error")

        self.update_word_count_display()
        self.save_settings()
        self.on_listbox_select(None)

    def clear_all_pdfs(self):
        """Clears all PDF files from the list."""
        if messagebox.askyesno("Clear All", "Are you sure you want to remove all PDF files?"):
            self.pdf_files.clear()
            self.pdf_listbox.delete(0, tk.END)
            self.total_word_count = 0
            self.update_word_count_display()
            self.save_settings()
            self.print_to_console("All PDF files cleared.", "info")
            self.on_listbox_select(None)

    def move_pdf_up(self):
        """Moves selected item up."""
        selected_indices = self.pdf_listbox.curselection()
        if not selected_indices: return
        index = selected_indices[0]
        if index > 0:
            self.pdf_files[index], self.pdf_files[index-1] = self.pdf_files[index-1], self.pdf_files[index]
            self.pdf_listbox.delete(index)
            self.pdf_listbox.insert(index-1, os.path.basename(self.pdf_files[index-1]))
            self.pdf_listbox.selection_set(index-1)
            self.save_settings()

    def move_pdf_down(self):
        """Moves selected item down."""
        selected_indices = self.pdf_listbox.curselection()
        if not selected_indices: return
        index = selected_indices[0]
        if index < len(self.pdf_files) - 1:
            self.pdf_files[index], self.pdf_files[index+1] = self.pdf_files[index+1], self.pdf_files[index]
            self.pdf_listbox.delete(index)
            self.pdf_listbox.insert(index+1, os.path.basename(self.pdf_files[index+1]))
            self.pdf_listbox.selection_set(index+1)
            self.save_settings()

    def select_output_folder(self):
        """Opens a dialog to select the output folder."""
        folder_selected = filedialog.askdirectory(initialdir=self.output_folder)
        if folder_selected:
            self.output_folder = folder_selected
            self.output_folder_label.config(text=self.output_folder)
            self.print_to_console(f"Output folder set to: {self.output_folder}", "info")
            self.save_settings()

    def update_ui_for_process(self, processing):
        """Updates UI state for start/stop of the merge process."""
        state = tk.DISABLED if processing else tk.NORMAL
        self.start_btn.config(state=tk.DISABLED if processing else tk.NORMAL)
        self.pause_btn.config(state=tk.NORMAL if processing else tk.DISABLED, text="Pause")
        self.stop_btn.config(state=tk.NORMAL if processing else tk.DISABLED)
        
        self.add_btn.config(state=state)
        self.pdf_listbox.config(state=state)
        self.select_folder_btn.config(state=state)
        self.remove_timestamps_checkbox.config(state=state)
        self.remove_images_checkbox.config(state=state)
        self.remove_pii_checkbox.config(state=state)
        self.custom_pii_entry.config(state=state)
        self.custom_pii_label.config(state=state)
        # New: Disable split controls during processing
        self.split_by_words_checkbox.config(state=state)
        self.split_word_count_entry.config(state=state)
        self.split_word_count_label.config(state=state)

        if not processing:
            self._update_pii_field_visibility()
            self._update_split_field_visibility()

        self.on_listbox_select(None)

    def start_merge(self):
        """Starts the merge process in a new thread."""
        global merge_thread, merge_running
        if merge_running:
            self.print_to_console("Merge process is already running.", "info")
            return
        if not self.pdf_files:
            messagebox.showerror("No Files", "Please add PDF files to the list first.")
            return
        
        # New: Validate split word count if enabled
        if self.split_by_words_var.get():
            try:
                word_limit = int(self.split_word_count_var.get())
                if word_limit <= 0:
                    messagebox.showerror("Invalid Input", "Word count for splitting must be a positive number.")
                    return
            except ValueError:
                messagebox.showerror("Invalid Input", "Word count for splitting must be a valid number.")
                return

        merge_stop_event.clear()
        merge_pause_event.clear()
        merge_running = True
        
        self.update_ui_for_process(processing=True)
        self.print_to_console("Starting PDF merge process...", "info")
        
        merge_thread = threading.Thread(target=self._merge_pdfs_threaded, daemon=True)
        merge_thread.start()

    def pause_merge(self):
        """Pauses or resumes the merge process."""
        global merge_paused
        if not merge_running: return
        merge_paused = not merge_paused
        if merge_paused:
            merge_pause_event.set()
            self.pause_btn.config(text="Resume")
            self.print_to_console("Merge process paused.", "info")
        else:
            merge_pause_event.clear()
            self.pause_btn.config(text="Pause")
            self.print_to_console("Merge process resumed.", "info")

    def stop_merge(self):
        """Stops the merge process."""
        if merge_running:
            merge_stop_event.set()
            self.print_to_console("Stopping merge process...", "info")

    def _get_output_filepath(self, counter=None):
        """Generates a unique output filename, with an optional counter for splitting."""
        base, ext = os.path.splitext(DEFAULT_OUTPUT_FILENAME)
        
        # New: Handle numbered files for splitting
        if counter is not None and counter > 1:
            base = f"{base}{counter}"
            
        output_filepath = os.path.join(self.output_folder, f"{base}{ext}")
        
        # Ensure the first file is also unique if it exists
        if counter is None or counter == 1:
            path_template = os.path.join(self.output_folder, base)
            file_counter = 1
            while os.path.exists(output_filepath):
                file_counter += 1
                output_filepath = f"{path_template}{file_counter}{ext}"
                
        return output_filepath

    def _scrub_pii_from_doc(self, doc):
        """
        Finds and applies redactions for PII in a PyMuPDF document object.
        Uses both Regex patterns and a custom string list for redaction.
        """
        self.print_to_console("    - Starting PII scrubbing...", "progress")
        total_redactions = 0
        
        custom_strings_raw = self.custom_pii_var.get()
        if custom_strings_raw:
            custom_strings = [s.strip() for s in custom_strings_raw.split(',') if s.strip()]
            if custom_strings:
                self.print_to_console(f"    - Searching for {len(custom_strings)} custom string(s)...", "progress")
                for page_num, page in enumerate(doc, 1):
                    for custom_string in custom_strings:
                        matches = page.search_for(custom_string)
                        if matches:
                            self.print_to_console(f"    - Found '{custom_string}' {len(matches)} time(s) on page {page_num}. Marking for redaction.", "progress")
                            for inst in matches:
                                page.add_redact_annot(inst, text=" ", fill=(0, 0, 0))
                            total_redactions += len(matches)

        pii_patterns = {
            "FULL_NAME": r'\b[A-Z]{4,}\s[A-Z]{4,}\b',
            "STREET_ADDRESS": r'\b\d{1,5}\s(?:[A-Z0-9]+\s?)+(?:STREET|ST|AVENUE|AVE|ROAD|RD|LANE|LN|DRIVE|DR|COURT|CT|PLACE|PL|BOULEVARD|BLVD)\b',
            "CITY_STATE_ZIP": r'\b[A-Z\s]+,\s[A-Z]{2}\s\d{5}(?:-\d{4})?\b',
            "ACCOUNT_NUMBER": r'\b\d{5}-\d{5}(?:-\d)?\b',
            "ID_NUMBER": r'\b\d{8,19}\b',
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        }
        
        for pii_type, pattern in pii_patterns.items():
            for page_num, page in enumerate(doc, 1):
                try:
                    matches = page.search_for(pattern)
                    if matches:
                        self.print_to_console(f"    - Found {len(matches)} potential '{pii_type}' on page {page_num}. Marking for redaction.", "progress")
                        for inst in matches:
                            page.add_redact_annot(inst, text=" ", fill=(0, 0, 0))
                        total_redactions += len(matches)
                except Exception as e:
                    self.print_to_console(f"    - Error searching for PII on page {page_num}: {e}", "error")

        if total_redactions > 0:
            self.print_to_console(f"    - Applying {total_redactions} total redactions...", "progress")
            for page in doc:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
            self.print_to_console("    - PII scrubbing complete.", "success")
        else:
            self.print_to_console("    - No PII matching the defined patterns or custom strings was found.", "warning")
            
        return doc

    def _merge_pdfs_threaded(self):
        """The core PDF processing and merging logic that runs in a thread."""
        global merge_running, merge_paused
        
        processed_temp_files = []
        try:
            # --- Stage 1: Pre-process all files (scrub, text-only, etc.) ---
            total_files = len(self.pdf_files)
            for i, pdf_path in enumerate(self.pdf_files):
                if merge_stop_event.is_set(): break
                while merge_pause_event.is_set(): time.sleep(0.1)

                self.print_to_console(f"Processing '{os.path.basename(pdf_path)}' ({i+1}/{total_files})...", "progress")
                
                doc_to_process = None
                try:
                    doc_to_process = fitz.open(pdf_path)

                    if self.remove_pii_var.get():
                        doc_to_process = self._scrub_pii_from_doc(doc_to_process)

                    if self.remove_images_var.get():
                        text_only_doc = fitz.open()
                        for page in doc_to_process:
                            page_text = page.get_text("text")
                            if self.remove_timestamps_var.get():
                                timestamp_regex = r'\[(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*(?:(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\]\s*'
                                page_text = re.sub(timestamp_regex, '', page_text)
                            
                            new_page = text_only_doc.new_page(width=page.rect.width, height=page.rect.height)
                            new_page.insert_text((50, 50), page_text, fontname="helv", fontsize=10)
                        
                        doc_to_process.close()
                        doc_to_process = text_only_doc

                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        temp_filename = tmp.name
                    
                    doc_to_process.save(temp_filename)
                    processed_temp_files.append(temp_filename)

                except Exception as e:
                    self.print_to_console(f"  Error processing '{os.path.basename(pdf_path)}': {e}. Skipping.", "error")
                    continue
                finally:
                    if doc_to_process and hasattr(doc_to_process, 'is_closed') and not doc_to_process.is_closed:
                        doc_to_process.close()
                
                progress_percent = int(((i + 1) / total_files) * 100)
                self.print_to_console(f"  Processing progress: {progress_percent}%", "progress")
            
            if merge_stop_event.is_set():
                self.print_to_console("Process stopped during file pre-processing.", "warning")
                raise SystemExit()
                
            # --- Stage 2: Final Merging (with or without splitting) ---
            if not processed_temp_files:
                self.print_to_console("No content was successfully processed to merge.", "warning")
                raise SystemExit()

            self.print_to_console("All files processed. Starting final merge...", "progress")
            
            # --- Splitting Logic ---
            if self.split_by_words_var.get():
                self._merge_with_splitting(processed_temp_files)
            # --- Standard Merging Logic ---
            else:
                self._merge_standard(processed_temp_files)

        except SystemExit: # Graceful exit on stop
             self.print_to_console("Merge process was stopped by user. No file saved.", "info")
        except Exception as e:
            self.print_to_console(f"An unexpected error occurred during the merge process: {e}", "error")
        finally:
            # Clean up temporary files
            for temp_path in processed_temp_files:
                try:
                    os.remove(temp_path)
                except OSError as e:
                    self.print_to_console(f"Error removing temporary file {temp_path}: {e}", "error")

            merge_running = False
            merge_paused = False
            self.master.after(0, lambda: self.update_ui_for_process(processing=False))

    def _merge_standard(self, temp_files):
        """Merges all temp files into a single output PDF."""
        final_merged_doc = fitz.open()
        for temp_path in temp_files:
            try:
                with fitz.open(temp_path) as temp_doc:
                    final_merged_doc.insert_pdf(temp_doc)
            except Exception as e:
                self.print_to_console(f"Could not merge temp file {os.path.basename(temp_path)}: {e}", "error")

        if len(final_merged_doc) > 0:
            output_filepath = self._get_output_filepath()
            final_merged_doc.save(output_filepath)
            self.print_to_console(f"Successfully merged PDFs to: {output_filepath}", "success")
        else:
            self.print_to_console("Final document is empty after merge attempts.", "warning")

        final_merged_doc.close()

    def _merge_with_splitting(self, temp_files):
        """Merges temp files into multiple PDFs, split by word count."""
        try:
            word_limit = int(self.split_word_count_var.get())
            self.print_to_console(f"Splitting output into files of approximately {word_limit} words.", "info")
        except ValueError:
            self.print_to_console("Invalid word count for splitting. Aborting.", "error")
            return
            
        output_doc = fitz.open()
        current_word_count = 0
        file_counter = 1
        files_saved = 0

        for temp_path in temp_files:
            if merge_stop_event.is_set(): break
            try:
                with fitz.open(temp_path) as temp_doc:
                    for page in temp_doc:
                        if merge_stop_event.is_set(): break
                        page_text = page.get_text("text")
                        page_word_count = self._count_words(page_text)
                        
                        # If adding this page exceeds the limit, save the current doc first
                        if current_word_count + page_word_count > word_limit and current_word_count > 0:
                            output_filepath = self._get_output_filepath(file_counter)
                            output_doc.save(output_filepath)
                            self.print_to_console(f"Saved split file: {os.path.basename(output_filepath)} ({current_word_count} words)", "success")
                            
                            output_doc.close()
                            output_doc = fitz.open()
                            current_word_count = 0
                            file_counter += 1
                            files_saved += 1
                        
                        # Add the page to the current output doc
                        output_doc.insert_pdf(temp_doc, from_page=page.number, to_page=page.number)
                        current_word_count += page_word_count
            except Exception as e:
                self.print_to_console(f"Error during splitting of {os.path.basename(temp_path)}: {e}", "error")

        # Save the last remaining document if it has content
        if not merge_stop_event.is_set() and len(output_doc) > 0:
            output_filepath = self._get_output_filepath(file_counter)
            output_doc.save(output_filepath)
            self.print_to_console(f"Saved final split file: {os.path.basename(output_filepath)} ({current_word_count} words)", "success")
            files_saved += 1

        if files_saved > 0:
            self.print_to_console(f"Successfully created {files_saved} split PDF files.", "success")
        else:
            self.print_to_console("No split files were generated.", "warning")
            
        output_doc.close()

def main():
    """Main function to create and run the Tkinter application."""
    root = tk.Tk()
    app = PDFMergerApp(root)
    
    def on_closing():
        if merge_running:
            merge_stop_event.set()
            if merge_thread:
                merge_thread.join(timeout=2) # Give thread time to stop
        app.save_settings() # Ensure settings are saved on close
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()