import os
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import json
import time
import threading
import winreg as reg
import zipfile

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Configuration
LOCAL_APP_DATA = os.environ.get('LOCALAPPDATA')
BASE_DIR = os.path.join(LOCAL_APP_DATA, 'rbxcr')
PRESETS_DIR = os.path.join(BASE_DIR, 'presets') 

TARGET_CURSORS = ['ArrowCursor.png', 'ArrowFarCursor.png', 'IBeamCursor.png']

class CursorChangerApp:
    def __init__(self, root, launch_file=None, start_minimized=False):
        self.root = root
        self.root.title("Roblox Cursor Replacer")
        
        # New proportional dimensions: 500x700
        self.root.geometry("500x700")
        self.root.resizable(False, False)
        
        # Set window icon from bundled assets
        icon_p = resource_path("icon.ico")
        if os.path.exists(icon_p):
            self.root.iconbitmap(icon_p)

        self.roblox_cursor_path = None
        self.selected_files = {name: None for name in TARGET_CURSORS}
        self.preview_labels = {name: None for name in TARGET_CURSORS}
        
        if not os.path.exists(PRESETS_DIR):
            os.makedirs(PRESETS_DIR)
        
        # Setup Registry & Unpack official presets
        self._setup_system_configs()
        self._unpack_bundled_presets()
        
        self._create_widgets()
        self._find_newest_roblox_path()
        self._load_current_roblox_previews()
        self._refresh_preset_menu()

        # Start the lightweight background watcher
        self.watcher_thread = threading.Thread(target=self._version_watcher, daemon=True)
        self.watcher_thread.start()

        # Handle direct file launch (.rbxcrp)
        if launch_file:
            self._handle_external_import(launch_file)
        
        # If started via Windows Startup, run in background
        if start_minimized:
            self.root.withdraw()

    def _setup_system_configs(self):
        """Registers file associations and startup entry in Windows Registry."""
        if not getattr(sys, 'frozen', False): return 
        exe_path = sys.executable
        try:
            # .rbxcrp File Association
            with reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\.rbxcrp") as key:
                reg.SetValue(key, "", reg.REG_SZ, "RobloxCursorPreset")
            with reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\RobloxCursorPreset\DefaultIcon") as key:
                reg.SetValue(key, "", reg.REG_SZ, f'"{exe_path}",0')
            with reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\RobloxCursorPreset\shell\open\command") as key:
                reg.SetValue(key, "", reg.REG_SZ, f'"{exe_path}" "%1"')
            
            # Windows Startup Entry
            with reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                reg.SetValueEx(key, "RBXCursorReplacer", 0, reg.REG_SZ, f'"{exe_path}" --silent')
        except Exception as e:
            print(f"Registry error: {e}")

    def _version_watcher(self):
        """Checks for Roblox updates every 60 seconds without using CPU resources."""
        last_version = None
        while True:
            self._find_newest_roblox_path()
            current_version = self.roblox_cursor_path
            if last_version and current_version != last_version:
                # Roblox updated! Re-apply user cursors automatically
                self._apply_changes(silent=True)
            last_version = current_version
            time.sleep(60)

    def _create_widgets(self):
        # Header
        tk.Label(self.root, text="Roblox Cursor Replacer", font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        # Main Cursor Previews
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(pady=2, padx=15, fill=tk.X)

        for name in TARGET_CURSORS:
            frame = tk.LabelFrame(self.main_frame, text=f" {name} ", padx=8, pady=2)
            frame.pack(pady=4, fill=tk.X)
            
            inner = tk.Frame(frame)
            inner.pack(fill=tk.X)
            
            self.preview_labels[name] = tk.Label(inner, text="[No Image]")
            self.preview_labels[name].pack(side=tk.LEFT, padx=5)
            
            tk.Button(inner, text="Browse", font=("Segoe UI", 9), 
                      command=lambda n=name: self._upload_image(n)).pack(side=tk.RIGHT, padx=5)

        # Options Section
        settings_frame = tk.LabelFrame(self.root, text=" Options ", padx=10, pady=5)
        settings_frame.pack(pady=10, padx=15, fill=tk.X)

        self.resize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Force Resize to 64x64 (f64)", variable=self.resize_var).pack(anchor="w")
        tk.Button(settings_frame, text="Hide to Background", command=self.root.withdraw).pack(anchor="w", pady=2)

        # Presets Section
        preset_frame = tk.LabelFrame(self.root, text=" Presets ", padx=10, pady=5)
        preset_frame.pack(pady=5, padx=15, fill=tk.X)

        self.preset_var = tk.StringVar(value="Select Preset")
        self.preset_menu = tk.OptionMenu(preset_frame, self.preset_var, "Default", command=self._on_preset_selected)
        self.preset_menu.pack(pady=5, fill=tk.X)

        btn_row = tk.Frame(preset_frame)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="Save Preset", command=self._export_preset).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        tk.Button(btn_row, text="Import Preset", command=self._import_preset).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Final Apply Button
        tk.Button(self.root, text="APPLY TO ROBLOX", bg="#28a745", fg="white", 
                  font=("Segoe UI", 11, "bold"), height=2, command=self._apply_changes).pack(pady=20, fill=tk.X, padx=30)

    def _unpack_bundled_presets(self):
        """Extracts bundled rbxcrp files from the EXE to the user directory."""
        bundled = ["2006-2013.rbxcrp", "2013-2021.rbxcrp"]
        for p in bundled:
            src = resource_path(p)
            dst = os.path.join(PRESETS_DIR, p)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

    def _update_preview(self, cursor_name, pil_image):
        """Updates the small UI thumbnail."""
        pil_image = pil_image.convert("RGBA")
        pil_image.thumbnail((40, 40), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(pil_image)
        self.preview_labels[cursor_name].config(image=tk_img, text="")
        self.preview_labels[cursor_name].image = tk_img

    def _find_newest_roblox_path(self):
        """Locates the active Roblox version directory."""
        if not LOCAL_APP_DATA: return
        v_dir = os.path.join(LOCAL_APP_DATA, 'Roblox', 'Versions')
        if not os.path.exists(v_dir): return
        vers = [os.path.join(v_dir, d) for d in os.listdir(v_dir) if d.lower().startswith('version')]
        if vers:
            self.roblox_cursor_path = os.path.join(max(vers, key=os.path.getmtime), 'content', 'textures', 'Cursors', 'KeyboardMouse')

    def _upload_image(self, cursor_name):
        path = filedialog.askopenfilename(filetypes=[("PNG Files", "*.png")])
        if path:
            self._update_preview(cursor_name, Image.open(path))
            self.selected_files[cursor_name] = path

    def _refresh_preset_menu(self):
        menu = self.preset_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="Current Roblox", command=tk._setit(self.preset_var, "Current Roblox", self._on_preset_selected))
        if os.path.exists(PRESETS_DIR):
            for file in sorted(os.listdir(PRESETS_DIR)):
                if file.endswith(".rbxcrp"):
                    menu.add_command(label=file, command=tk._setit(self.preset_var, file, self._on_preset_selected))

    def _export_preset(self):
        name = simpledialog.askstring("Save Preset", "Enter preset name:")
        if not name: return
        if not name.endswith(".rbxcrp"): name += ".rbxcrp"
        save_path = os.path.join(PRESETS_DIR, name)
        meta = {"f64": self.resize_var.get()}
        with zipfile.ZipFile(save_path, 'w') as zipf:
            zipf.writestr('metadata.json', json.dumps(meta))
            for c, p in self.selected_files.items():
                if p and os.path.exists(p): zipf.write(p, c)
        self._refresh_preset_menu()

    def _import_preset(self):
        path = filedialog.askopenfilename(filetypes=[("RBXCR Preset", "*.rbxcrp")])
        if path:
            shutil.copy2(path, os.path.join(PRESETS_DIR, os.path.basename(path)))
            self._refresh_preset_menu()

    def _handle_external_import(self, path):
        """Helper for double-click file association imports."""
        dest = os.path.join(PRESETS_DIR, os.path.basename(path))
        if not os.path.exists(dest): shutil.copy2(path, dest)
        self._refresh_preset_menu()
        self.preset_var.set(os.path.basename(path))
        self._on_preset_selected(os.path.basename(path))

    def _on_preset_selected(self, filename):
        """Extracts and previews a .rbxcrp file."""
        if filename == "Current Roblox":
            self._load_current_roblox_previews()
            return
        p_path = os.path.join(PRESETS_DIR, filename)
        tmp = os.path.join(BASE_DIR, "temp")
        if os.path.exists(tmp): shutil.rmtree(tmp)
        os.makedirs(tmp)
        with zipfile.ZipFile(p_path, 'r') as z:
            z.extractall(tmp)
            m_p = os.path.join(tmp, 'metadata.json')
            if os.path.exists(m_p):
                with open(m_p, 'r') as f: self.resize_var.set(json.load(f).get("f64", True))
            for c in TARGET_CURSORS:
                img_p = os.path.join(tmp, c)
                if os.path.exists(img_p):
                    persist = os.path.join(PRESETS_DIR, f"active_{c}")
                    shutil.copy2(img_p, persist)
                    self._update_preview(c, Image.open(persist))
                    self.selected_files[c] = persist
        shutil.rmtree(tmp)

    def _load_current_roblox_previews(self):
        if not self.roblox_cursor_path: return
        for n in TARGET_CURSORS:
            p = os.path.join(self.roblox_cursor_path, n)
            if os.path.exists(p):
                self._update_preview(n, Image.open(p))
                self.selected_files[n] = p

    def _apply_changes(self, silent=False):
        """The core logic that modifies the actual Roblox texture files."""
        if not self.roblox_cursor_path: return
        try:
            for n, s in self.selected_files.items():
                if s:
                    d = os.path.join(self.roblox_cursor_path, n)
                    if self.resize_var.get():
                        with Image.open(s) as img: 
                            img.resize((64, 64), Image.Resampling.LANCZOS).save(d, "PNG")
                    else: 
                        shutil.copy2(s, d)
            if not silent: messagebox.showinfo("Success", "Cursors updated successfully!")
        except Exception as e:
            if not silent: messagebox.showerror("Error", f"Failed to apply: {e}")

if __name__ == "__main__":
    args = sys.argv[1:]
    is_silent = "--silent" in args
    launch = next((a for a in args if a.endswith(".rbxcrp")), None)
    
    root = tk.Tk()
    app = CursorChangerApp(root, launch_file=launch, start_minimized=is_silent)
    root.mainloop()
