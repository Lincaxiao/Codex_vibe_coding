from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf


class AudioServiceError(Exception):
    pass


class AudioService:
    def __init__(self, sample_rate: int, channels: int, dtype: str = "float32") -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.input_device_index: int | None = None
        self._stream = None
        self._frames: List[np.ndarray] = []
        self._last_status = ""

    def set_input_device(self, device_index: int | None) -> None:
        self.input_device_index = device_index

    def list_input_devices(self) -> list[tuple[int, str]]:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover
            raise AudioServiceError("sounddevice is not available in this environment.") from exc

        devices = sd.query_devices()
        result: list[tuple[int, str]] = []
        for index, device in enumerate(devices):
            max_input_channels = int(device.get("max_input_channels", 0))
            if max_input_channels > 0:
                name = str(device.get("name", f"Device {index}"))
                result.append((index, name))
        return result

    def get_default_input_device(self) -> int | None:
        try:
            import sounddevice as sd
        except Exception:
            return None

        default_value = sd.default.device
        if isinstance(default_value, (tuple, list)):
            device_index = default_value[0]
        else:
            device_index = default_value

        if device_index is None:
            return None

        try:
            index_int = int(device_index)
        except (TypeError, ValueError):
            return None

        return index_int if index_int >= 0 else None

    def start_recording(self) -> None:
        if self._stream is not None:
            raise AudioServiceError("Recording is already in progress.")

        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover
            raise AudioServiceError("sounddevice is not available in this environment.") from exc

        self._frames = []
        self._last_status = ""

        def _callback(indata, _frames, _time, status) -> None:
            if status:
                self._last_status = str(status)
            self._frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=self.input_device_index,
                callback=_callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            self._frames = []
            selected = (
                "系统默认设备"
                if self.input_device_index is None
                else f"设备索引 {self.input_device_index}"
            )
            raise AudioServiceError(
                f"Unable to start recording with {selected}. Check microphone permissions and input device settings."
            ) from exc

    def stop_and_save(self, output_wav_path: Path) -> Path:
        if self._stream is None:
            raise AudioServiceError("No active recording session.")

        try:
            self._stream.stop()
            self._stream.close()
        except Exception as exc:
            raise AudioServiceError("Unable to stop recording cleanly.") from exc
        finally:
            self._stream = None

        if not self._frames:
            self._frames = []
            raise AudioServiceError("No audio data was captured.")

        audio_data = np.concatenate(self._frames, axis=0)
        self._frames = []

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            sf.write(str(output_wav_path), audio_data, self.sample_rate)
        except Exception as exc:
            raise AudioServiceError(f"Failed to write WAV file: {output_wav_path}") from exc

        return output_wav_path

    def abort_recording(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None
            self._frames = []
