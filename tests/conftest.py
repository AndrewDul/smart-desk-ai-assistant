from __future__ import annotations

import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


try:
    import sounddevice as _sounddevice  # noqa: F401
except ModuleNotFoundError:
    sounddevice_stub = types.ModuleType("sounddevice")

    class PortAudioError(Exception):
        pass

    class _DummyInputStream:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def close(self) -> None:
            return None

    def _return_none(*args, **kwargs):
        return None

    def _return_empty_list(*args, **kwargs):
        return []

    sounddevice_stub.PortAudioError = PortAudioError
    sounddevice_stub.InputStream = _DummyInputStream
    sounddevice_stub.RawInputStream = _DummyInputStream
    sounddevice_stub.query_devices = _return_empty_list
    sounddevice_stub.check_input_settings = _return_none
    sounddevice_stub.rec = _return_empty_list
    sounddevice_stub.wait = _return_none
    sounddevice_stub.stop = _return_none
    sounddevice_stub.sleep = _return_none
    sounddevice_stub.default = types.SimpleNamespace(device=None)

    sys.modules["sounddevice"] = sounddevice_stub