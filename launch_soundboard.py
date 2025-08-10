import subprocess
import sys
import logging
from main import ensure_pipewire_virtual_source, cleanup_pipewire_virtual_source

logging.basicConfig(
    filename='launcher.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Setting up PipeWire virtual devices...")
    try:
        ensure_pipewire_virtual_source()
    except Exception as e:
        logger.error(f"Error setting up PipeWire devices: {e}")
    try:
        logger.info("Launching soundboard app subprocess...")
        proc = subprocess.Popen([sys.executable, 'main.py'])
        proc.wait()
    finally:
        logger.info("Cleaning up PipeWire virtual devices...")
        try:
            cleanup_pipewire_virtual_source()
        except Exception as e:
            logger.error(f"Error cleaning up PipeWire devices: {e}")

if __name__ == "__main__":
    main()
