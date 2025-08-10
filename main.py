import sys
import subprocess
from soundboard_db import SoundboardDB
import numpy as np
import soundfile as sf
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QFileDialog, QInputDialog,
    QMainWindow, QMenuBar, QMenu, QMessageBox, QVBoxLayout, QComboBox
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import sounddevice as sd
from sounddevice import PortAudioError

def ensure_pipewire_virtual_source():
    try:
        sinks = subprocess.check_output(["pactl", "list", "short", "sinks"]).decode()
        sources = subprocess.check_output(["pactl", "list", "short", "sources"]).decode()
        if "SoundboardSink" not in sinks:
            subprocess.run([
                "pactl", "load-module", "module-null-sink",
                "sink_name=SoundboardSink",
                "sink_properties=device.description=SoundboardSink"
            ], check=True)
        if "SoundboardSource" not in sources:
            subprocess.run([
                "pactl", "load-module", "module-remap-source",
                "master=SoundboardSink.monitor",
                "source_name=SoundboardSource",
                "source_properties=device.description=SoundboardSource"
            ], check=True)
    except Exception as e:
        print(f"Warning: Could not set up PipeWire virtual source: {e}")

def cleanup_pipewire_virtual_source():
    try:
        modules = subprocess.check_output(["pactl", "list", "short", "modules"]).decode()
        for line in modules.splitlines():
            if ("module-null-sink" in line and "SoundboardSink" in line) or ("module-remap-source" in line and "SoundboardSource" in line):
                module_id = line.split()[0]
                subprocess.run(["pactl", "unload-module", module_id], check=True)
    except Exception as e:
        print(f"Warning: Could not clean up PipeWire virtual source: {e}")

class SoundButton(QPushButton):
    def __init__(self, label, board, audio_path=None):
        super().__init__(label, board.central)
        self.audio_path = audio_path
        self.board = board
        self.clicked.connect(self.play_sound)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)

    def to_dict(self):
        return {
            'label': self.text(),
            'audio_path': self.audio_path
        }

    @staticmethod
    def from_dict(data, board, row, col):
        return SoundButton(data['label'], board, data.get('audio_path'))

    def play_sound(self):
        if self.audio_path:
            data, fs = sf.read(self.audio_path, dtype='float32')
            device_idx = self.board.output_device
            try:
                device_info = sd.query_devices(device_idx, 'output')
                device_rate = int(device_info['default_samplerate'])
                if fs != device_rate:
                    duration = data.shape[0] / fs
                    new_length = int(duration * device_rate)
                    if data.ndim == 1:
                        data = np.interp(np.linspace(0, len(data), new_length, endpoint=False), np.arange(len(data)), data)
                    else:
                        data = np.stack([
                            np.interp(np.linspace(0, len(data), new_length, endpoint=False), np.arange(len(data)), data[:, ch])
                            for ch in range(data.shape[1])
                        ], axis=-1)
                    fs = device_rate
                # Ensure data is float32 before playback
                data = np.asarray(data, dtype=np.float32)
                with sd.OutputStream(samplerate=fs, device=device_idx, channels=data.shape[1] if data.ndim > 1 else 1) as stream:
                    stream.write(data)
            except PortAudioError as e:
                QMessageBox.critical(self, "Playback Error", f"Could not play sound.\nError: {e}\nTry converting your audio file to a standard sample rate like 48000 Hz or check your PipeWire device settings.")
            except Exception as e:
                QMessageBox.critical(self, "Playback Error", f"Could not play sound.\nError: {e}")
        else:
            QMessageBox.information(self, "No Sound", "No audio file assigned to this button.")

    def open_menu(self, pos):
        menu = QMenu(self)
        assign_action = QAction("Assign Sound & Label", self)
        remove_action = QAction("Remove Button", self)
        menu.addAction(assign_action)
        menu.addAction(remove_action)
        action = menu.exec(self.mapToGlobal(pos))
        if action == assign_action:
            file, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.wav *.mp3 *.ogg)")
            if file:
                self.audio_path = file
                text, ok = QInputDialog.getText(self, "Button Label", "Enter new label:", text=self.text())
                if ok and text:
                    self.setText(text)
        elif action == remove_action:
            self.board.remove_button(self)

class SoundBoard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pySoundBoard")
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout()
        self.central.setLayout(self.main_layout)
        self.device_dropdown = self.create_device_dropdown()
        self.main_layout.addWidget(self.device_dropdown)
        self.layout = QGridLayout()
        self.main_layout.addLayout(self.layout)
        self.buttons = []
        self.db = SoundboardDB()
        print("[DEBUG] Available devices:")
        for idx, dev in enumerate(sd.query_devices()):
            print(f"  [{idx}] {dev['name']} (max output channels: {dev['max_output_channels']}, max input channels: {dev['max_input_channels']})")
        # Restore last selected device if available
        saved_device = self.db.get_setting('audio_device')
        self.output_device = int(saved_device) if saved_device is not None else self.get_pipewire_device()
        self.device_dropdown.setCurrentIndex(self.output_device if self.output_device is not None else 0)
        print(f"[DEBUG] Selected output device index: {self.output_device}")
        if self.output_device is not None:
            dev = sd.query_devices(self.output_device)
            print(f"[DEBUG] Output device name: {dev['name']}")
        self.rows = 3
        self.cols = 3
        self.current_config_id = None
        self.init_menu()
        self.load_last_used_config()

    def create_device_dropdown(self):
        device_box = QComboBox()
        self.device_names = []
        self.device_indices = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev['max_output_channels'] > 0:
                label = f"{dev['name']} (idx {idx})"
                device_box.addItem(label)
                self.device_names.append(dev['name'])
                self.device_indices.append(idx)
        device_box.currentIndexChanged.connect(self.on_device_selected)
        return device_box

    def on_device_selected(self, idx):
        if 0 <= idx < len(self.device_indices):
            self.output_device = self.device_indices[idx]
            print(f"[DEBUG] User selected output device: {self.device_names[idx]} (idx {self.output_device})")
            self.db.set_setting('audio_device', self.output_device)

    def init_menu(self):
        menubar = self.menuBar()
        board_menu = menubar.addMenu("Menu")
        add_btn_action = QAction("Add Button", self)
        add_btn_action.triggered.connect(self.add_button_dialog)
        save_action = QAction("Save Config", self)
        save_action.triggered.connect(self.save_config_dialog)
        load_action = QAction("Switch Config", self)
        load_action.triggered.connect(self.switch_config_dialog)
        export_action = QAction("Export Config to JSON", self)
        export_action.triggered.connect(self.export_config_json)
        import_action = QAction("Import Config from JSON", self)
        import_action.triggered.connect(self.import_config_json)
        board_menu.addAction(add_btn_action)
        board_menu.addAction(save_action)
        board_menu.addAction(load_action)
        board_menu.addAction(export_action)
        board_menu.addAction(import_action)
    def export_config_json(self):
        if not self.current_config_id:
            QMessageBox.information(self, "No Config", "No configuration loaded.")
            return
        btns = self.db.get_config_buttons(self.current_config_id)
        layout_data = {
            'rows': self.rows,
            'cols': self.cols,
            'buttons': [
                {'row': row, 'col': col, 'label': label, 'audio_path': audio_path}
                for (label, audio_path, row, col) in btns
            ]
        }
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "soundboard.json", "JSON Files (*.json)")
        if path:
            import json
            with open(path, 'w') as f:
                json.dump(layout_data, f, indent=2)

    def import_config_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "JSON Files (*.json)")
        if not path:
            return
        import json
        with open(path, 'r') as f:
            layout_data = json.load(f)
        btns = layout_data.get('buttons', [])
        self.rows = layout_data.get('rows', 3)
        self.cols = layout_data.get('cols', 3)
        # Ask for config name
        text, ok = QInputDialog.getText(self, "Import Config", "Enter name for imported configuration:")
        if ok and text:
            btn_dicts = [
                {'label': b['label'], 'audio_path': b.get('audio_path'), 'row': b['row'], 'col': b['col']}
                for b in btns
            ]
            config_id = self.db.save_config(text, btn_dicts, self.rows, self.cols)
            self.db.set_last_used_config(config_id)
            self.current_config_id = config_id
            self.init_ui([(b['label'], b.get('audio_path'), b['row'], b['col']) for b in btns])

    def init_ui(self, buttons=None):
        # Remove existing buttons
        for (btn, _, _) in self.buttons:
            self.layout.removeWidget(btn)
            btn.deleteLater()
        self.buttons.clear()
        # Add buttons from config or default
        if buttons:
            for btn_data in buttons:
                btn = SoundButton(btn_data[0], self, btn_data[1])
                self.layout.addWidget(btn, btn_data[2], btn_data[3])
                self.buttons.append((btn, btn_data[2], btn_data[3]))
        else:
            for i in range(self.rows):
                for j in range(self.cols):
                    self.add_button(i, j)

    def add_button(self, row, col, label=None, audio_path=None):
        label = label or f"Button {row*self.cols+col+1}"
        btn = SoundButton(label, self, audio_path)
        self.layout.addWidget(btn, row, col)
        self.buttons.append((btn, row, col))

    def add_button_dialog(self):
        positions = [(i, j) for i in range(self.rows) for j in range(self.cols)]
        used = {(self.layout.getItemPosition(i)[0], self.layout.getItemPosition(i)[1]) for i in range(self.layout.count())}
        free = [pos for pos in positions if pos not in used]
        if not free:
            self.rows += 1
            row, col = self.rows-1, 0
        else:
            row, col = free[0]
        text, ok = QInputDialog.getText(self, "Button Label", "Enter label for new button:")
        if ok and text:
            file, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.wav *.mp3 *.ogg)")
            if file:
                self.add_button(row, col, text, file)

    def remove_button(self, btn):
        idx = self.layout.indexOf(btn)
        if idx != -1:
            self.layout.removeWidget(btn)
            btn.deleteLater()
            self.buttons = [(b, r, c) for (b, r, c) in self.buttons if b != btn]

    def save_config_dialog(self):
        text, ok = QInputDialog.getText(self, "Save Config", "Enter configuration name:")
        if ok and text:
            btns = [
                {'label': btn.text(), 'audio_path': btn.audio_path, 'row': row, 'col': col}
                for (btn, row, col) in self.buttons
            ]
            config_id = self.db.save_config(text, btns, self.rows, self.cols)
            self.db.set_last_used_config(config_id)
            self.current_config_id = config_id

    def switch_config_dialog(self):
        configs = self.db.get_all_configs()
        if not configs:
            QMessageBox.information(self, "No Configs", "No configurations found.")
            return
        items = [name for (_, name) in configs]
        idx, ok = QInputDialog.getItem(self, "Switch Config", "Select configuration:", items, editable=False)
        if ok:
            config_id = configs[items.index(idx)][0]
            self.db.set_last_used_config(config_id)
            self.current_config_id = config_id
            btns = self.db.get_config_buttons(config_id)
            self.init_ui(btns)
    def load_last_used_config(self):
        config = self.db.get_last_used_config()
        if config:
            self.current_config_id = config[0]
            btns = self.db.get_config_buttons(config[0])
            self.init_ui(btns)
        else:
            self.init_ui()

    def get_pipewire_device(self):
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            if 'SoundboardSink' in dev['name']:
                return idx
        for idx, dev in enumerate(devices):
            if 'pipewire' in dev['name'].lower():
                return idx
        for idx, dev in enumerate(devices):
            if 'default' in dev['name'].lower():
                return idx
        return 0

if __name__ == "__main__":
    from PyQt6.QtCore import QCoreApplication, Qt
    import atexit
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    ensure_pipewire_virtual_source()
    atexit.register(cleanup_pipewire_virtual_source)
    app = QApplication(sys.argv)
    win = SoundBoard()
    win.show()
sys.exit(app.exec())
