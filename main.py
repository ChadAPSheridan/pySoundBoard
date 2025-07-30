import sys
import subprocess
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QFileDialog, QInputDialog,
    QMainWindow, QMenuBar, QMenu, QMessageBox, QVBoxLayout
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import sounddevice as sd
from sounddevice import PortAudioError
import numpy as np
import soundfile as sf
def ensure_pipewire_virtual_source():
    # Check if SoundboardSink and SoundboardSource exist
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
    # Check if SoundboardSink and SoundboardSource exist
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
    # Unload modules for SoundboardSink and SoundboardSource
    try:
        modules = subprocess.check_output(["pactl", "list", "short", "modules"]).decode()
        for line in modules.splitlines():
            if ("module-null-sink" in line and "SoundboardSink" in line) or ("module-remap-source" in line and "SoundboardSource" in line):
                module_id = line.split()[0]
                subprocess.run(["pactl", "unload-module", module_id], check=True)
    except Exception as e:
        print(f"Warning: Could not clean up PipeWire virtual source: {e}")

import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QFileDialog, QInputDialog,
    QMainWindow, QMenuBar, QMenu, QMessageBox, QVBoxLayout
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import sounddevice as sd
import numpy as np
import soundfile as sf

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
            device_info = sd.query_devices(self.board.output_device, 'output')
            device_rate = int(device_info['default_samplerate'])
            if fs != device_rate:
                # Resample using numpy
                duration = data.shape[0] / fs
                new_length = int(duration * device_rate)
                if data.ndim == 1:
                    data = np.interp(np.linspace(0, len(data), new_length, endpoint=False), np.arange(len(data)), data)
                else:
                    # For stereo or multi-channel
                    data = np.stack([
                        np.interp(np.linspace(0, len(data), new_length, endpoint=False), np.arange(len(data)), data[:, ch])
                        for ch in range(data.shape[1])
                    ], axis=-1)
                fs = device_rate
            try:
                with sd.OutputStream(samplerate=fs, device=self.board.output_device, channels=data.shape[1] if data.ndim > 1 else 1) as stream:
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


import sys
import subprocess
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QFileDialog, QInputDialog,
    QMainWindow, QMenuBar, QMenu, QMessageBox, QVBoxLayout
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import sounddevice as sd
import numpy as np
import soundfile as sf

def ensure_pipewire_virtual_source():
    # Check if SoundboardSink and SoundboardSource exist
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
        self.layout = QGridLayout()
        self.central.setLayout(self.layout)
        self.buttons = []
        self.output_device = self.get_pipewire_device()
        self.rows = 3
        self.cols = 3
        self.init_menu()
        self.init_ui()

    def init_menu(self):
        menubar = self.menuBar()
        board_menu = menubar.addMenu("Menu")
        add_btn_action = QAction("Add Button", self)
        add_btn_action.triggered.connect(self.add_button_dialog)
        save_action = QAction("Save Layout", self)
        save_action.triggered.connect(self.save_layout)
        load_action = QAction("Load Layout", self)
        load_action.triggered.connect(self.load_layout)
        board_menu.addAction(add_btn_action)
        board_menu.addAction(save_action)
        board_menu.addAction(load_action)

    def init_ui(self):
        for i in range(self.rows):
            for j in range(self.cols):
                self.add_button(i, j)

    def add_button(self, row, col, label=None, audio_path=None):
        label = label or f"Button {row*self.cols+col+1}"
        btn = SoundButton(label, self, audio_path)
        self.layout.addWidget(btn, row, col)
        self.buttons.append((btn, row, col))

    def add_button_dialog(self):
        # Find next available grid position
        positions = [(i, j) for i in range(self.rows) for j in range(self.cols)]
        used = {(self.layout.getItemPosition(i)[0], self.layout.getItemPosition(i)[1]) for i in range(self.layout.count())}
        free = [pos for pos in positions if pos not in used]
        if not free:
            # Add new row if grid is full
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

    def save_layout(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Layout", "soundboard.json", "JSON Files (*.json)")
        if not path:
            return
        layout_data = {
            'rows': self.rows,
            'cols': self.cols,
            'buttons': [
                {'row': row, 'col': col, **btn.to_dict()}
                for (btn, row, col) in self.buttons
            ]
        }
        with open(path, 'w') as f:
            json.dump(layout_data, f, indent=2)

    def load_layout(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Layout", "", "JSON Files (*.json)")
        if not path:
            return
        with open(path, 'r') as f:
            layout_data = json.load(f)
        # Remove all current buttons
        for (btn, _, _) in self.buttons:
            self.layout.removeWidget(btn)
            btn.deleteLater()
        self.buttons.clear()
        self.rows = layout_data.get('rows', 3)
        self.cols = layout_data.get('cols', 3)
        for btn_data in layout_data['buttons']:
            btn = SoundButton(btn_data['label'], self, btn_data.get('audio_path'))
            self.layout.addWidget(btn, btn_data['row'], btn_data['col'])
            self.buttons.append((btn, btn_data['row'], btn_data['col']))

    def get_pipewire_device(self):
        # Try to find a PipeWire virtual source
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            if 'SoundboardSink' in dev['name'] or 'SoundboardSource' in dev['name']:
                return idx
        return None  # Default device

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
