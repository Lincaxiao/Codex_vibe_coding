import sys
from types import SimpleNamespace

from src.services.audio_service import AudioService


class _FakeSoundDevice:
    def __init__(self, devices: list[dict], default_device):
        self._devices = devices
        self.default = SimpleNamespace(device=default_device)

    def query_devices(self, device_index=None):
        if device_index is None:
            return self._devices
        if not isinstance(device_index, int) or device_index < 0 or device_index >= len(self._devices):
            raise RuntimeError("invalid device index")
        return self._devices[device_index]


def test_ensure_input_device_falls_back_to_default(monkeypatch) -> None:
    fake_sd = _FakeSoundDevice(
        devices=[
            {"name": "Mic A", "max_input_channels": 1},
            {"name": "Mic B", "max_input_channels": 1},
        ],
        default_device=(1, None),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    service = AudioService(sample_rate=16000, channels=1)
    service.set_input_device(99)

    is_ready, detail, switched = service.ensure_input_device_available()

    assert is_ready is True
    assert switched is True
    assert service.input_device_index is None
    assert "已自动切换为系统默认设备" in detail


def test_ensure_input_device_falls_back_to_first_available_when_default_missing(monkeypatch) -> None:
    fake_sd = _FakeSoundDevice(
        devices=[
            {"name": "Output only", "max_input_channels": 0},
            {"name": "Mic A", "max_input_channels": 1},
            {"name": "Mic B", "max_input_channels": 1},
        ],
        default_device=(-1, -1),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    service = AudioService(sample_rate=16000, channels=1)
    service.set_input_device(7)

    is_ready, detail, switched = service.ensure_input_device_available()

    assert is_ready is True
    assert switched is True
    assert service.input_device_index == 1
    assert "已自动切换到可用设备索引 1" in detail


def test_ensure_input_device_fails_when_no_input_device(monkeypatch) -> None:
    fake_sd = _FakeSoundDevice(
        devices=[
            {"name": "Output A", "max_input_channels": 0},
            {"name": "Output B", "max_input_channels": 0},
        ],
        default_device=(-1, -1),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    service = AudioService(sample_rate=16000, channels=1)
    service.set_input_device(None)

    is_ready, detail, switched = service.ensure_input_device_available()

    assert is_ready is False
    assert switched is False
    assert "没有可用的录音输入设备" in detail
