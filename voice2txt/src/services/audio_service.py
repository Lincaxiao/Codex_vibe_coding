from pathlib import Path
from threading import Lock
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
        self._level_lock = Lock()
        self._latest_rms = 0.0
        self._latest_peak = 0.0

    def set_input_device(self, device_index: int | None) -> None:
        self.input_device_index = device_index

    def validate_input_device(self) -> tuple[bool, str]:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover
            return False, f"sounddevice is not available: {exc}"

        selected_device = self.input_device_index
        if selected_device is None:
            selected_device = self.get_default_input_device()
            if selected_device is None:
                return False, "未检测到系统默认输入设备。"

        try:
            info = sd.query_devices(selected_device)
        except Exception as exc:
            return False, f"无法访问输入设备 {selected_device}: {exc}"

        max_input_channels = int(info.get("max_input_channels", 0))
        if max_input_channels <= 0:
            return False, f"设备 {selected_device} 不支持录音输入。"

        return True, "设备可用。"

    def ensure_input_device_available(self) -> tuple[bool, str, bool]:
        """Ensure a usable input device is selected.

        Returns:
            (is_ready, detail, switched)
            switched=True means input_device_index was adjusted for recovery.
        """
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover
            return False, f"sounddevice is not available: {exc}", False

        try:
            devices = sd.query_devices()
        except Exception as exc:
            return False, f"无法读取输入设备列表：{exc}", False

        input_indices: list[int] = []
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) > 0:
                input_indices.append(index)

        if not input_indices:
            return False, "当前没有可用的录音输入设备。", False

        selected_device = self.input_device_index
        if selected_device is not None:
            is_ok, detail = self._is_device_usable(sd, selected_device)
            if is_ok:
                return True, "设备可用。", False

            default_device = self.get_default_input_device()
            if default_device is not None:
                default_ok, _ = self._is_device_usable(sd, default_device)
                if default_ok:
                    self.input_device_index = None
                    return (
                        True,
                        f"{detail} 已自动切换为系统默认设备。",
                        True,
                    )

            fallback_index = input_indices[0]
            self.input_device_index = fallback_index
            return (
                True,
                f"{detail} 已自动切换到可用设备索引 {fallback_index}。",
                True,
            )

        default_device = self.get_default_input_device()
        if default_device is not None:
            default_ok, default_detail = self._is_device_usable(sd, default_device)
            if default_ok:
                return True, "设备可用。", False

            fallback_index = input_indices[0]
            self.input_device_index = fallback_index
            return (
                True,
                f"{default_detail} 已自动切换到可用设备索引 {fallback_index}。",
                True,
            )

        fallback_index = input_indices[0]
        self.input_device_index = fallback_index
        return True, f"未检测到系统默认输入设备，已自动切换到设备索引 {fallback_index}。", True

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
        self._set_levels(0.0, 0.0)

        def _callback(indata, _frames, _time, status) -> None:
            if status:
                self._last_status = str(status)
            frame = indata.copy()
            self._frames.append(frame)
            if frame.size == 0:
                self._set_levels(0.0, 0.0)
                return
            # Capture lightweight live level metrics for UI polling.
            abs_frame = np.abs(frame)
            peak = float(abs_frame.max())
            rms = float(np.sqrt(np.mean(frame * frame)))
            self._set_levels(rms=rms, peak=peak)

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
            self._set_levels(0.0, 0.0)
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
        self._set_levels(0.0, 0.0)

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
            self._set_levels(0.0, 0.0)

    def get_live_levels(self) -> tuple[float, float]:
        with self._level_lock:
            return self._latest_rms, self._latest_peak

    def _set_levels(self, rms: float, peak: float) -> None:
        with self._level_lock:
            self._latest_rms = max(0.0, rms)
            self._latest_peak = max(0.0, peak)

    @staticmethod
    def _is_device_usable(sd, device_index: int) -> tuple[bool, str]:
        try:
            info = sd.query_devices(device_index)
        except Exception as exc:
            return False, f"无法访问输入设备 {device_index}: {exc}"

        max_input_channels = int(info.get("max_input_channels", 0))
        if max_input_channels <= 0:
            return False, f"设备 {device_index} 不支持录音输入。"
        return True, "设备可用。"
