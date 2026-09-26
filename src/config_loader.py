"""Safe loader and writer for mommy-pulsy's Lua-shaped configuration.

The configuration format intentionally supports only a small, data-only subset of Lua:
``return { key = value, nested = { ... } }``.  This avoids executing arbitrary Lua while
keeping ``mommie.lua`` pleasant to edit by hand.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""


class ConfigLoadError(Exception):
    """Raised when configuration cannot be parsed or written."""


class _LuaDataParser:
    """Very small parser for the data-only Lua syntax used by mommie.lua."""

    _number_re = re.compile(r"(?:[-+]?\d+(?:\.\d*)?|[-+]?\.\d+)(?:[eE][-+]?\d+)?")
    _identifier_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def parse(self) -> Dict[str, Any]:
        self._skip_ws_comments()
        if self._match_keyword("return"):
            self._skip_ws_comments()
        value = self._parse_table()
        self._skip_ws_comments()
        if self.pos != self.length:
            raise ConfigLoadError(self._error("Unexpected content after configuration"))
        if not isinstance(value, dict):
            raise ConfigLoadError(self._error("Configuration should return a table, honey."))
        return value

    def _error(self, message: str) -> str:
        line = self.text.count("\n", 0, self.pos) + 1
        return f"{message} (line {line})"

    def _skip_ws_comments(self) -> None:
        while self.pos < self.length:
            if self.text[self.pos].isspace():
                self.pos += 1
                continue
            if self.text.startswith("--", self.pos):
                newline = self.text.find("\n", self.pos + 2)
                self.pos = self.length if newline == -1 else newline + 1
                continue
            break

    def _match_keyword(self, keyword: str) -> bool:
        end = self.pos + len(keyword)
        if self.text[self.pos:end] != keyword:
            return False
        before_ok = self.pos == 0 or not (self.text[self.pos - 1].isalnum() or self.text[self.pos - 1] == "_")
        after_ok = end >= self.length or not (self.text[end].isalnum() or self.text[end] == "_")
        if before_ok and after_ok:
            self.pos = end
            return True
        return False

    def _parse_table(self) -> Dict[str, Any]:
        self._skip_ws_comments()
        if self.pos >= self.length or self.text[self.pos] != "{":
            raise ConfigLoadError(self._error("Expected '{' for configuration table"))
        self.pos += 1
        result: Dict[str, Any] = {}

        while True:
            self._skip_ws_comments()
            if self.pos >= self.length:
                raise ConfigLoadError(self._error("Unclosed configuration table"))
            if self.text[self.pos] == "}":
                self.pos += 1
                return result

            key = self._parse_key()
            self._skip_ws_comments()
            if self.pos >= self.length or self.text[self.pos] != "=":
                raise ConfigLoadError(self._error("Expected '=' after configuration key"))
            self.pos += 1
            value = self._parse_value()
            if key in result:
                raise ConfigLoadError(self._error(f"Duplicate configuration key '{key}'"))
            result[key] = value

            self._skip_ws_comments()
            if self.pos < self.length and self.text[self.pos] == ",":
                self.pos += 1
                continue
            if self.pos < self.length and self.text[self.pos] == "}":
                self.pos += 1
                return result
            raise ConfigLoadError(self._error("Expected ',' or '}' in configuration table"))

    def _parse_key(self) -> str:
        self._skip_ws_comments()
        if self.pos < self.length and self.text[self.pos] in ('"', "'"):
            return self._parse_string()
        match = self._identifier_re.match(self.text, self.pos)
        if not match:
            raise ConfigLoadError(self._error("Expected a configuration key"))
        self.pos = match.end()
        return match.group(0)

    def _parse_value(self) -> Any:
        self._skip_ws_comments()
        if self.pos >= self.length:
            raise ConfigLoadError(self._error("Expected a configuration value"))
        char = self.text[self.pos]
        if char == "{":
            return self._parse_table()
        if char in ('"', "'"):
            return self._parse_string()
        if self._match_keyword("true"):
            return True
        if self._match_keyword("false"):
            return False
        if self._match_keyword("nil"):
            return None

        match = self._number_re.match(self.text, self.pos)
        if match:
            raw = match.group(0)
            self.pos = match.end()
            try:
                value = float(raw)
                return int(value) if value.is_integer() else value
            except ValueError as exc:
                raise ConfigLoadError(self._error("Invalid number")) from exc

        raise ConfigLoadError(self._error("Only data values are allowed in mommie.lua"))

    def _parse_string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'"}
        while self.pos < self.length:
            char = self.text[self.pos]
            self.pos += 1
            if char == quote:
                return "".join(out)
            if char == "\\":
                if self.pos >= self.length:
                    raise ConfigLoadError(self._error("Unfinished string escape"))
                escaped = self.text[self.pos]
                self.pos += 1
                if escaped not in escapes:
                    raise ConfigLoadError(self._error(f"Unsupported string escape '\\{escaped}'"))
                out.append(escapes[escaped])
            else:
                out.append(char)
        raise ConfigLoadError(self._error("Unclosed string"))


class ConfigLoader:
    """Loads, validates, and atomically writes ``mommie.lua``."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / ".config" / "mommy-pulsy" / "mommie.lua"
        self.config_path = Path(self.config_path)

    def _validate_number(
        self,
        value: Any,
        field_name: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigValidationError(f"`{field_name}` is supposed to be a number, honey.")
        result = float(value)
        if not (result == result and abs(result) != float("inf")):
            raise ConfigValidationError(f"`{field_name}` must be a finite number, sweetheart.")
        if min_val is not None and result < min_val:
            raise ConfigValidationError(f"`{field_name}` should be at least {min_val}, sweetheart.")
        if max_val is not None and result > max_val:
            raise ConfigValidationError(f"`{field_name}` should be at most {max_val}, darling.")
        return result

    def _validate_integer(
        self,
        value: Any,
        field_name: str,
        min_val: Optional[int] = None,
        max_val: Optional[int] = None,
    ) -> int:
        number = self._validate_number(value, field_name, min_val, max_val)
        if not number.is_integer():
            raise ConfigValidationError(f"`{field_name}` should be a whole number, sweetheart.")
        return int(number)

    def _validate_string(self, value: Any, field_name: str, allowed: Optional[set[str]] = None) -> str:
        if not isinstance(value, str):
            raise ConfigValidationError(f"`{field_name}` is supposed to be a string, honey.")
        if allowed is not None and value not in allowed:
            choices = ", ".join(sorted(allowed))
            raise ConfigValidationError(f"`{field_name}` should be one of {{{choices}}}, sweetheart.")
        return value

    def _validate_bool(self, value: Any, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise ConfigValidationError(f"`{field_name}` is supposed to be a boolean, honey.")
        return value

    def _validate_table(self, value: Any, field_name: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigValidationError(f"`{field_name}` is supposed to be a table, honey.")
        return value

    def _validate_pulse_config(self, pulse: Dict[str, Any]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        if "attack" in pulse:
            result["attack"] = self._validate_number(pulse["attack"], "pulse.attack", 0.001, 5.0)
        if "decay" in pulse:
            result["decay"] = self._validate_number(pulse["decay"], "pulse.decay", 0.001, 5.0)
        if "height" in pulse:
            result["height"] = self._validate_number(pulse["height"], "pulse.height", 0.1, 10.0)
        if "threshold" in pulse:
            result["threshold"] = self._validate_number(
                pulse["threshold"], "pulse.threshold", 0.0, 0.5
            )
        if "transient_gain" in pulse:
            result["transient_gain"] = self._validate_number(
                pulse["transient_gain"], "pulse.transient_gain", 0.0, 10.0
            )
        if "bass_weight" in pulse:
            result["bass_weight"] = self._validate_number(
                pulse["bass_weight"], "pulse.bass_weight", 0.0, 1.0
            )
        if "event_threshold" in pulse:
            result["event_threshold"] = self._validate_number(
                pulse["event_threshold"], "pulse.event_threshold", 0.0, 1.0
            )
        if "overshoot_ratio" in pulse:
            result["overshoot_ratio"] = self._validate_number(
                pulse["overshoot_ratio"], "pulse.overshoot_ratio", 0.0, 1.0
            )
        return result

    def _validate_frequency_config(self, frequency: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if "min" in frequency:
            result["min"] = self._validate_number(frequency["min"], "frequency.min", 1, 20000)
        if "max" in frequency:
            result["max"] = self._validate_number(frequency["max"], "frequency.max", 1, 24000)
        if "curve" in frequency:
            result["curve"] = self._validate_string(frequency["curve"], "frequency.curve", {"linear", "logarithmic"})
        if "min" in result and "max" in result and result["min"] >= result["max"]:
            raise ConfigValidationError("frequency.min should be less than frequency.max, darling.")
        return result

    def _validate_recovery_config(self, recovery: Dict[str, Any]) -> Dict[str, bool]:
        result: Dict[str, bool] = {}
        if "enabled" in recovery:
            result["enabled"] = self._validate_bool(recovery["enabled"], "recovery.enabled")
        if "auto_restore" in recovery:
            result["auto_restore"] = self._validate_bool(recovery["auto_restore"], "recovery.auto_restore")
        return result

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(config, dict):
            raise ConfigValidationError("Configuration should be a table, honey.")
        result: Dict[str, Any] = {}
        if "sensitivity" in config:
            result["sensitivity"] = self._validate_number(config["sensitivity"], "sensitivity", 0.0, 10.0)
        if "smoothing" in config:
            result["smoothing"] = self._validate_number(config["smoothing"], "smoothing", 0.0, 1.0)
        if "decay" in config:
            result["decay"] = self._validate_number(config["decay"], "decay", 0.0, 1.0)
        if "fps" in config:
            result["fps"] = self._validate_integer(config["fps"], "fps", 1, 240)
        if "audio" in config:
            audio = self._validate_table(config["audio"], "audio")
            result["audio"] = self._validate_audio_config(audio)
        if "pulse" in config:
            result["pulse"] = self._validate_pulse_config(self._validate_table(config["pulse"], "pulse"))
        if "frequency" in config:
            result["frequency"] = self._validate_frequency_config(self._validate_table(config["frequency"], "frequency"))
        if "recovery" in config:
            result["recovery"] = self._validate_recovery_config(self._validate_table(config["recovery"], "recovery"))

        # The effective frequency range must still contain FFT bins at the configured
        # sample rate. This prevents a valid-looking config from producing an empty
        # analysis range when audio.sample_rate is lowered.
        audio_cfg = result.get("audio", {})
        freq_cfg = result.get("frequency", {})
        sample_rate = int(audio_cfg.get("sample_rate", 48000))
        nyquist = sample_rate / 2.0
        frequency_min = float(freq_cfg.get("min", 20))
        frequency_max = min(float(freq_cfg.get("max", 20000)), nyquist)
        if frequency_min >= frequency_max:
            raise ConfigValidationError(
                "frequency.min must be below the usable frequency.max/Nyquist, darling."
            )
        return result

    def _validate_audio_config(self, audio: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if "sample_rate" in audio:
            result["sample_rate"] = self._validate_integer(audio["sample_rate"], "audio.sample_rate", 8000, 192000)
        if "channels" in audio:
            result["channels"] = self._validate_integer(audio["channels"], "audio.channels", 1, 8)
        if "chunk_size" in audio:
            result["chunk_size"] = self._validate_integer(audio["chunk_size"], "audio.chunk_size", 128, 8192)
        if "queue_size" in audio:
            result["queue_size"] = self._validate_integer(audio["queue_size"], "audio.queue_size", 2, 32)
        if "backend" in audio:
            result["backend"] = self._validate_string(audio["backend"], "audio.backend", {"auto", "pipewire", "pulseaudio"})
        return result

    def load_detailed(self) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        """Load a config and return a human-readable validation/parse diagnostic."""
        if not self.config_path.exists():
            return {}, False, f"Configuration file not found: {self.config_path}"

        try:
            text = self.config_path.read_text(encoding="utf-8")
            parsed = _LuaDataParser(text).parse()
            return self.validate_config(parsed), True, None
        except ConfigValidationError as exc:
            return {}, False, str(exc)
        except ConfigLoadError as exc:
            return {}, False, str(exc)
        except OSError as exc:
            return {}, False, f"Failed to read mommie.lua: {exc}"

    def load(self) -> Tuple[Dict[str, Any], bool]:
        config, valid, _ = self.load_detailed()
        return config, valid

    def save_atomic(self, config: Dict[str, Any]) -> None:
        validated = self.validate_config(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[str] = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix=".mommie.lua.", suffix=".tmp", dir=self.config_path.parent)
            os.close(fd)
            with os.fdopen(os.open(temp_path, os.O_WRONLY | os.O_TRUNC), "w", encoding="utf-8") as handle:
                handle.write("return ")
                self._write_lua_table(handle, validated)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.config_path)
            temp_path = None
            try:
                dir_fd = os.open(self.config_path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        except Exception as exc:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise ConfigLoadError(f"Failed to save configuration atomically: {exc}") from exc

    def _write_lua_table(self, handle, value: Any, indent: int = 0) -> None:
        if isinstance(value, dict):
            handle.write("{\n")
            items = list(value.items())
            for index, (key, item) in enumerate(items):
                handle.write("    " * (indent + 1))
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
                    handle.write(str(key))
                else:
                    escaped_key = str(key).replace("\\", "\\\\").replace('"', '\\"')
                    handle.write(f'"{escaped_key}"')
                handle.write(" = ")
                self._write_lua_table(handle, item, indent + 1)
                if index != len(items) - 1:
                    handle.write(",")
                handle.write("\n")
            handle.write("    " * indent + "}")
        elif isinstance(value, bool):
            handle.write("true" if value else "false")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            handle.write(repr(value))
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            handle.write(f'"{escaped}"')
        elif value is None:
            handle.write("nil")
        else:
            raise ConfigLoadError(f"Unsupported configuration value type: {type(value).__name__}")
