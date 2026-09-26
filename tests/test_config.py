"""
Tests for configuration loading and validation.
"""

import pytest
import tempfile
from pathlib import Path
from src.config_loader import ConfigLoader, ConfigValidationError, ConfigLoadError


class TestConfigLoader:
    """Test configuration loader."""

    def test_load_valid_config(self):
        """Test loading a valid configuration."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write("""
return {
    sensitivity = 1.0,
    smoothing = 0.75,
    fps = 120,
    pulse = {
        attack = 0.02,
        decay = 0.18,
    },
}
""")
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert is_valid
            assert config['sensitivity'] == 1.0
            assert config['smoothing'] == 0.75
            assert config['fps'] == 120
            assert config['pulse']['attack'] == 0.02
            assert config['pulse']['decay'] == 0.18
        finally:
            temp_path.unlink()

    def test_load_invalid_number_type(self):
        """Test that invalid number types are rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { fps = "not a number" }')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert not is_valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_out_of_range(self):
        """Test that out-of-range values are rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { fps = 500 }')  # fps max is 240
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert not is_valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_invalid_string_value(self):
        """Test that invalid string values are rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { frequency = { curve = "invalid" } }')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert not is_valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_invalid_bool_type(self):
        """Test that invalid boolean types are rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { recovery = { enabled = "true" } }')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert not is_valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_min_greater_than_max(self):
        """Test that frequency min > max is rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { frequency = { min = 20000, max = 20 } }')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert not is_valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_nonexistent_file(self):
        """Test loading a nonexistent file."""
        loader = ConfigLoader(Path("/nonexistent/path/mommie.lua"))
        config, is_valid = loader.load()

        assert not is_valid
        assert config == {}

    def test_save_atomic(self):
        """Test atomic save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "mommie.lua"

            loader = ConfigLoader(temp_path)
            config = {
                'sensitivity': 1.5,
                'fps': 60,
            }

            loader.save_atomic(config)

            assert temp_path.exists()

            # Verify we can load it back
            new_loader = ConfigLoader(temp_path)
            loaded_config, is_valid = new_loader.load()

            assert is_valid
            assert loaded_config['sensitivity'] == 1.5
            assert loaded_config['fps'] == 60

    def test_save_creates_directory(self):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "subdir" / "mommie.lua"

            loader = ConfigLoader(temp_path)
            config = {'fps': 120}

            loader.save_atomic(config)

            assert temp_path.exists()
            assert temp_path.parent.exists()

    def test_partial_config(self):
        """Test that partial configurations are handled correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { sensitivity = 2.0 }')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert is_valid
            assert config['sensitivity'] == 2.0
            # Default values should not be added by validator
            assert 'fps' not in config
        finally:
            temp_path.unlink()

    def test_empty_config(self):
        """Test that empty configuration is valid."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return {}')
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = ConfigLoader(temp_path)
            config, is_valid = loader.load()

            assert is_valid
            assert config == {}
        finally:
            temp_path.unlink()


    def test_detailed_error_identifies_invalid_sensitivity(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { sensitivity = "banana" }')
            f.flush()
            temp_path = Path(f.name)
        try:
            loader = ConfigLoader(temp_path)
            config, valid, error = loader.load_detailed()
            assert not valid
            assert config == {}
            assert error is not None
            assert "sensitivity" in error
        finally:
            temp_path.unlink()

    def test_fractional_fps_is_rejected(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { fps = 60.5 }')
            f.flush()
            temp_path = Path(f.name)
        try:
            loader = ConfigLoader(temp_path)
            config, valid = loader.load()
            assert not valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_threshold_accepts_rms_noise_floor(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { pulse = { threshold = 0.004 } }')
            f.flush()
            temp_path = Path(f.name)
        try:
            loader = ConfigLoader(temp_path)
            config, valid = loader.load()
            assert valid
            assert config['pulse']['threshold'] == pytest.approx(0.004)
        finally:
            temp_path.unlink()


    def test_sensitivity_out_of_range_is_rejected(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { sensitivity = 50 }')
            f.flush()
            temp_path = Path(f.name)
        try:
            loader = ConfigLoader(temp_path)
            config, valid = loader.load()
            assert not valid
            assert config == {}
        finally:
            temp_path.unlink()

    def test_smoothing_out_of_range_is_rejected(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write('return { smoothing = 1.5 }')
            f.flush()
            temp_path = Path(f.name)
        try:
            loader = ConfigLoader(temp_path)
            config, valid = loader.load()
            assert not valid
            assert config == {}
        finally:
            temp_path.unlink()
