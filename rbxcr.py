import os
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import json
import uuid
import zipfile
import winreg as reg

def resource_path(relative_path):
    try:
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
    def __init__(self, root, launch_file=None):
        self.root = root
        self.root.title("Roblox Cursor Manager - felfel")
        self.root.geometry("600x850")
        
        # Set window icon (if icon.ico is bundled)
        icon_p = resource_path("icon.ico")
        if os.path.exists(icon_p):
            self.root.iconbitmap(icon_p)

        self.roblox_cursor_path = None
        self.selected_files = {name: None for name in TARGET_CURSORS}
        self.preview_labels = {name: None for name in TARGET_CURSORS}
        
        if not os.path.exists(PRESETS_DIR):
            os.makedirs(PRESETS_DIR)
        
        self._setup_file_association()
        self._unpack_bundled_presets()
        self._create_widgets()
        self._find_newest_roblox_path()
        self._load_current_roblox_previews()
        self._refresh_preset_menu()

        if launch_file and launch_file.lower().endswith(".rbxcrp"):
            self._handle_external_import(launch_file)

    def _setup_file_association(self):
        """Registers .rbxcrp files to open with this EXE and uses the icon."""
        if not getattr(sys, 'frozen', False):
            return 

        exe_path = sys.executable
        icon_path = f'"{exe_path}",0' # Index 0 is the main icon of the EXE

        try:
            # 1. Associate .rbxcrp with a ProgID
            with reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\.rbxcrp") as key:
                reg.SetValue(key, "", reg.REG_SZ, "RobloxCursorPreset")

            # 2. Define the ProgID
            prog_id_path = r"Software\Classes\RobloxCursorPreset"
            with reg.CreateKey(reg.HKEY_CURRENT_USER, prog_id_path) as key:
                reg.SetValue(key, "", reg.REG_SZ, "Roblox Cursor Preset File")

            # 3. Set the Icon for the file type
            with reg.CreateKey(reg.HKEY_CURRENT_USER, f"{prog_id_path}\\DefaultIcon") as key:
                reg.SetValue(key, "", reg.REG_SZ, icon_path)

            # 4. Set the Open Command
            with reg.CreateKey(reg.HKEY_CURRENT_USER, f"{prog_id_path}\\shell\\open\\command") as key:
                reg.SetValue(key, "", reg.REG_SZ, f'"{exe_path}" "%1"')
                
        except Exception as e:
            print(f"Registry error: {e}")

    def _handle_external_import(self, path):
        dest = os.path.join(PRESETS_DIR, os.path.basename(path))
        if not os.path.exists(dest):
            shutil.copy2(path, dest)
        self._refresh_preset_menu()
        self.preset_var.set(os.path.basename(path))
        self._on_preset_selected(os.path.basename(path))
        messagebox.showinfo("Imported", f"Preset '{os.path.basename(path)}' imported!")

    def _unpack_bundled_presets(self):
        bundled_presets = ["2006-2013.rbxcrp", "2013-2021.rbxcrp", "2021.rbxcrp"]
        for p_name in bundled_presets:
            internal_path = resource_path(p_name)
            external_path = os.path.join(PRESETS_DIR, p_name)
            if os.path.exists(internal_path) and not os.path.exists(external_path):
                shutil.copy2(internal_path, external_path)

    def _create_widgets(self):
        tk.Label(self.root, text="Roblox Cursor Customizer", font=("Segoe UI", 16, "bold")).pack(pady=10)
        
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(pady=5, padx=20, fill=tk.X)

        for name in TARGET_CURSORS:
            frame = tk.LabelFrame(self.main_frame, text=f" {name} ", padx=10, pady=5)
            frame.pack(pady=5, fill=tk.X)
            self.preview_labels[name] = tk.Label(frame, text="[Current]")
            self.preview_labels[name].pack(pady=5)
            tk.Button(frame, text="Change PNG", command=lambda n=name: self._upload_image(n)).pack(pady=2)

        settings_frame = tk.LabelFrame(self.root, text=" Settings ", padx=10, pady=10)
        settings_frame.pack(pady=15, padx=20, fill=tk.X)

        self.resize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Force Resize to 64x64 (f64)", variable=self.resize_var).pack(anchor="w")

        preset_frame = tk.LabelFrame(self.root, text=" Presets (.rbxcrp) ", padx=10, pady=10)
        preset_frame.pack(pady=10, padx=20, fill=tk.X)

        self.preset_var = tk.StringVar(value="Select Preset")
        self.preset_menu = tk.OptionMenu(preset_frame, self.preset_var, "Default", command=self._on_preset_selected)
        self.preset_menu.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        tk.Button(preset_frame, text="Save As", command=self._export_preset).pack(side=tk.LEFT, padx=2)
        tk.Button(preset_frame, text="Import", command=self._import_preset).pack(side=tk.LEFT, padx=2)

        tk.Button(self.root, text="APPLY TO ROBLOX", bg="#28a745", fg="white", 
                  font=("Segoe UI", 12, "bold"), height=2, command=self._apply_changes).pack(pady=20, fill=tk.X, padx=40)

    def _find_newest_roblox_path(self):
        if not LOCAL_APP_DATA: return
        v_dir = os.path.join(LOCAL_APP_DATA, 'Roblox', 'Versions')
        if not os.path.exists(v_dir): return
        vers = [os.path.join(v_dir, d) for d in os.listdir(v_dir) if d.lower().startswith('version')]
        if vers:
            self.roblox_cursor_path = os.path.join(max(vers, key=os.path.getmtime), 'content', 'textures', 'Cursors', 'KeyboardMouse')

    def _update_preview(self, cursor_name, pil_image):
        pil_image = pil_image.convert("RGBA")
        pil_image.thumbnail((50, 50), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(pil_image)
        self.preview_labels[cursor_name].config(image=tk_img, text="")
        self.preview_labels[cursor_name].image = tk_img

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
            for file in os.listdir(PRESETS_DIR):
                if file.endswith(".rbxcrp"):
                    menu.add_command(label=file, command=tk._setit(self.preset_var, file, self._on_preset_selected))

    def _export_preset(self):
        name = simpledialog.askstring("Save Preset", "Enter preset name:")
        if not name: return
        if not name.endswith(".rbxcrp"): name += ".rbxcrp"
        save_path = os.path.join(PRESETS_DIR, name)
        metadata = {"f64": self.resize_var.get()}
        with zipfile.ZipFile(save_path, 'w') as zipf:
            zipf.writestr('metadata.json', json.dumps(metadata))
            for cname, path in self.selected_files.items():
                if path and os.path.exists(path):
                    zipf.write(path, cname)
        self._refresh_preset_menu()

    def _import_preset(self):
        path = filedialog.askopenfilename(filetypes=[("RBXCR Preset", "*.rbxcrp")])
        if path:
            shutil.copy2(path, os.path.join(PRESETS_DIR, os.path.basename(path)))
            self._refresh_preset_menu()

    def _on_preset_selected(self, filename):
        if filename == "Current Roblox":
            self._load_current_roblox_previews()
            return
        preset_path = os.path.join(PRESETS_DIR, filename)
        temp_extract = os.path.join(BASE_DIR, "temp_extract")
        if os.path.exists(temp_extract): shutil.rmtree(temp_extract)
        os.makedirs(temp_extract)
        with zipfile.ZipFile(preset_path, 'r') as zipf:
            zipf.extractall(temp_extract)
            meta_path = os.path.join(temp_extract, 'metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    data = json.load(f)
                    self.resize_var.set(data.get("f64", True))
            for cname in TARGET_CURSORS:
                img_p = os.path.join(temp_extract, cname)
                if os.path.exists(img_p):
                    persistent_path = os.path.join(PRESETS_DIR, f"last_used_{cname}")
                    shutil.copy2(img_p, persistent_path)
                    self._update_preview(cname, Image.open(persistent_path))
                    self.selected_files[cname] = persistent_path
        shutil.rmtree(temp_extract)

    def _load_current_roblox_previews(self):
        if not self.roblox_cursor_path: return
        for name in TARGET_CURSORS:
            p = os.path.join(self.roblox_cursor_path, name)
            if os.path.exists(p):
                self._update_preview(name, Image.open(p))
                self.selected_files[name] = p

    def _apply_changes(self):
        if not self.roblox_cursor_path: return
        if messagebox.askyesno("Confirm", "Apply to Roblox?"):
            for name, src in self.selected_files.items():
                if src:
                    dest = os.path.join(self.roblox_cursor_path, name)
                    if self.resize_var.get():
                        with Image.open(src) as img:
                            img.resize((64, 64), Image.Resampling.LANCZOS).save(dest, "PNG")
                    else:
                        shutil.copy2(src, dest)
            messagebox.showinfo("Done", "Updated!")

if __name__ == "__main__":
    launch_file = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    app = CursorChangerApp(root, launch_file=launch_file)
    root.mainloop()