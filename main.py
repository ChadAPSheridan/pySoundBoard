import sys
import subprocess
import logging
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

# Set up logging to file
logging.basicConfig(
    filename='app.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

class DeviceComboBox(QComboBox):
    def __init__(self, parent=None, populate_callback=None):
        super().__init__(parent)
        self.populate_callback = populate_callback

    def showPopup(self):
        if self.populate_callback:
            self.populate_callback(self)
        super().showPopup()


def ensure_pipewire_virtual_source():
    logger.debug("Starting PipeWire virtual source setup...")
    try:
        sinks = subprocess.check_output(["pactl", "list", "short", "sinks"]).decode()
        logger.debug(f"Sinks: {sinks}")
        sources = subprocess.check_output(["pactl", "list", "short", "sources"]).decode()
        logger.debug(f"Sources: {sources}")
        modules = subprocess.check_output(["pactl", "list", "short", "modules"]).decode()
        logger.debug(f"Modules: {modules}")
        # Create null sink for soundboard
        if "SoundboardSink" not in sinks:
            logger.debug("Creating SoundboardSink...")
            subprocess.run([
                "pactl", "load-module", "module-null-sink",
                "sink_name=SoundboardSink",
                "sink_properties=device.description=SoundboardSink"
            ], check=True)
        # Get default mic
        mic_source = subprocess.check_output(["pactl", "get-default-source"]).decode().strip()
        logger.debug(f"Default mic source: {mic_source}")
        # Create null sink for mix
        if "SoundboardMix" not in sinks:
            logger.debug("Creating SoundboardMix...")
            subprocess.run([
                "pactl", "load-module", "module-null-sink",
                "sink_name=SoundboardMix",
                "sink_properties=device.description=SoundboardMix"
            ], check=True)
        # Loopback soundboard to mix
        if "module-loopback" not in modules or "SoundboardSink.monitor" not in modules or "SoundboardMix" not in modules:
            logger.debug("Loopback SoundboardSink.monitor to SoundboardMix...")
            subprocess.run([
                "pactl", "load-module", "module-loopback",
                "source=SoundboardSink.monitor",
                "sink=SoundboardMix"
            ], check=True)
        # Loopback mic to mix
        if "module-loopback" not in modules or mic_source not in modules or "SoundboardMix" not in modules:
            logger.debug(f"Loopback {mic_source} to SoundboardMix...")
            subprocess.run([
                "pactl", "load-module", "module-loopback",
                f"source={mic_source}",
                f"sink=SoundboardMix"
            ], check=True)
        # Remap mix monitor as source
        if "SoundboardMixSource" not in sources:
            logger.debug("Remapping SoundboardMix.monitor as SoundboardMixSource...")
            subprocess.run([
                "pactl", "load-module", "module-remap-source",
                "master=SoundboardMix.monitor",
                "source_name=SoundboardMixSource",
                "source_properties=device.description=SoundboardMixSource"
            ], check=True)
        logger.debug("PipeWire virtual source setup complete.")
    except Exception as e:
        logger.warning(f"Could not set up PipeWire virtual source: {e}")

def cleanup_pipewire_virtual_source():
    try:
        modules = subprocess.check_output(["pactl", "list", "short", "modules"]).decode()
        for line in modules.splitlines():
            if ("module-null-sink" in line and ("SoundboardSink" in line or "SoundboardMix" in line)) or \
               ("module-remap-source" in line and ("SoundboardSource" in line or "SoundboardMixSource" in line)) or \
               ("module-loopback" in line):
                module_id = line.split()[0]
                subprocess.run(["pactl", "unload-module", module_id], check=True)
    except Exception as e:
        logger.warning(f"Could not clean up PipeWire virtual source: {e}")

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
                # Log device info before playback
                try:
                    device_info = sd.query_devices(device_idx, 'output')
                    logger.debug(f"Attempting playback on device idx {device_idx}: {device_info['name']} (max output channels: {device_info['max_output_channels']})")
                except Exception as info_err:
                    logger.error(f"Error querying device info for idx {device_idx}: {info_err}")
                    raise
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
                logger.error(f"Playback error: {e}")
                QMessageBox.critical(self, "Playback Error", f"Could not play sound.\nError: {e}\nTry converting your audio file to a standard sample rate like 48000 Hz or check your PipeWire device settings.")
            except Exception as e:
                logger.error(f"Playback error: {e}")
                QMessageBox.critical(self, "Playback Error", f"Could not play sound.\nError: {e}")
        else:
            logger.info("No audio file assigned to this button.")
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
    def check_unsaved_changes(self):
        if not self.current_config_id:
            return False
        # Get current config from DB
        db_btns = self.db.get_config_buttons(self.current_config_id)
        db_layout = {
            (row, col): (label, audio_path)
            for (label, audio_path, row, col) in db_btns
        }
        # Get current UI config
        ui_layout = {
            (row, col): (btn.text(), btn.audio_path)
            for (btn, row, col) in self.buttons
        }
        # Compare
        if db_layout != ui_layout:
            reply = QMessageBox.question(self, "Save Config?", "Do you want to save your current configuration?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self.save_config_dialog()
    def __init__(self):
        logger.debug("Initializing SoundBoard app...")
        super().__init__()
        ensure_pipewire_virtual_source()  # Ensure virtual sink/source is set up before device dropdown
        logger.debug("Creating main window and layout...")
        self.setWindowTitle("pySoundBoard")
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout()
        self.central.setLayout(self.main_layout)
        logger.debug("Creating output device dropdown...")
        self.output_device_dropdown = self.create_device_dropdown(device_type='output')
        self.main_layout.addWidget(self.output_device_dropdown)
        logger.debug("Creating grid layout for buttons...")
        self.layout = QGridLayout()
        self.main_layout.addLayout(self.layout)
        self.buttons = []
        self.db = SoundboardDB()
        logger.debug("Querying available devices:")
        for idx, dev in enumerate(sd.query_devices()):
            logger.debug(f"  [{idx}] {dev['name']} (max output channels: {dev['max_output_channels']}, max input channels: {dev['max_input_channels']})")
        logger.debug("Binding output to SoundboardSink...")
        self.output_device = self.get_pipewire_device()
        self.output_device_dropdown.setCurrentIndex(self.output_device)
        logger.debug(f"Selected output device index: {self.output_device}")
        if self.output_device is not None:
            dev = sd.query_devices(self.output_device)
            logger.debug(f"Output device name: {dev['name']}")
        self.rows = 3
        self.cols = 3
        self.current_config_id = None
        self.current_config_name = None
        logger.debug("Initializing menu...")
        self.init_menu()
        logger.debug("Loading last used config...")
        self.load_last_used_config()
        logger.debug("SoundBoard app initialization complete.")

    def create_device_dropdown(self, device_type='output'):
        device_box = DeviceComboBox(populate_callback=self.populate_device_dropdown)
        self.populate_device_dropdown(device_box)
        device_box.currentIndexChanged.connect(self.on_output_device_selected)
        return device_box

    def populate_device_dropdown(self, device_box):
        import sys
        import re
        import subprocess
        device_box.clear()
        names = []
        indices = []
        # Run 'python -m sounddevice' in a subprocess and parse output
        device_box.clear()
        names = []
        indices = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev['max_output_channels'] > 0:
                label = f"{dev['name']} (idx {idx})"
                device_box.addItem(label)
                names.append(dev['name'])
                indices.append(idx)
                logger.debug(f"Device {idx}: {dev['name']} (max output channels: {dev['max_output_channels']})")
        self.output_device_names = names
        self.output_device_indices = indices

    def on_output_device_selected(self, idx):
        if 0 <= idx < len(self.output_device_indices):
            self.output_device = self.output_device_indices[idx]
            logger.debug(f"User selected output device: {self.output_device_names[idx]} (idx {self.output_device})")
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
        new_config_action = QAction("New Config", self)
        new_config_action.triggered.connect(self.new_config_dialog)
        board_menu.addAction(add_btn_action)
        board_menu.addAction(save_action)
        board_menu.addAction(load_action)
        board_menu.addAction(export_action)
        board_menu.addAction(import_action)
        board_menu.addAction(new_config_action)


    def new_config_dialog(self):
        # Prompt to save if there are unsaved changes
        self.check_unsaved_changes()

        # Load default config (3x3 grid, default labels)
        self.rows = 3
        self.cols = 3
        self.current_config_id = None
        self.current_config_name = None
        self.init_ui()
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
            self.current_config_name = text
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
        text, ok = QInputDialog.getText(
            self,
            "Save Config",
            "Enter configuration name:",
            text=self.current_config_name if self.current_config_name else ""
        )
        if ok and text:
            btns = [
                {'label': btn.text(), 'audio_path': btn.audio_path, 'row': row, 'col': col}
                for (btn, row, col) in self.buttons
            ]
            config_id = self.db.save_config(text, btns, self.rows, self.cols)
            self.db.set_last_used_config(config_id)
            self.current_config_id = config_id
            self.current_config_name = text

    def switch_config_dialog(self):
        # Prompt to save if there are unsaved changes
        self.check_unsaved_changes()
        configs = self.db.get_all_configs()
        if not configs:
            QMessageBox.information(self, "No Configs", "No configurations found.")
            return
        items = [name for (_, name) in configs]
        idx, ok = QInputDialog.getItem(self, "Switch Config", "Select configuration:", items, editable=False)
        if ok:
            config_index = items.index(idx)
            config_id, config_name = configs[config_index]
            self.db.set_last_used_config(config_id)
            self.current_config_id = config_id
            self.current_config_name = config_name
            btns = self.db.get_config_buttons(config_id)
            self.init_ui(btns)
    def load_last_used_config(self):
        config = self.db.get_last_used_config()
        if config:
            self.current_config_id = config[0]
            self.current_config_name = config[1] if len(config) > 1 else None
            btns = self.db.get_config_buttons(config[0])
            self.init_ui(btns)
        else:
            self.current_config_name = None
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

    def closeEvent(self, event):
        self.check_unsaved_changes()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    app = QApplication(sys.argv)
    win = SoundBoard()
    win.show()
    sys.exit(app.exec())
