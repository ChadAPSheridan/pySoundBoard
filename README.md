# pySoundBoard

A customizable soundboard application for KDE Plasma 6.4 on Arch Linux, built with Python and PyQt6. Audio output is routed to a PipeWire virtual input, making it available as a microphone in other applications.

## Features
- Customizable buttons for assigning audio files
- Modern PyQt6 GUI for KDE Plasma
- Audio output routed to a PipeWire input (virtual microphone)

## Requirements
- Python 3.10+
- PyQt6
- sounddevice or PyAudio
- numpy
- PipeWire (with virtual source configured)

## Setup
1. Install dependencies:
   ```sh
   pip install PyQt6 sounddevice numpy
   ```
2. (Optional) Set up a PipeWire virtual source (see below).

## PipeWire Virtual Source
To create a virtual microphone for the soundboard, use:
```sh
pactl load-module module-null-sink sink_name=SoundboardSink sink_properties=device.description=SoundboardSink
pactl load-module module-remap-source master=SoundboardSink.monitor source_name=SoundboardSource source_properties=device.description=SoundboardSource
```
Then, select `SoundboardSource` as the input device in your target application.

## Usage
- Run the application:
  ```sh
  python main.py
  ```
- Add audio files to buttons and play them. Audio will be routed to the virtual input.

## License
MIT
