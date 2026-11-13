from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path

import pytest

from sc_foundation import DateHelper, JSONEncoder

JSON_FILE = "tests/test_json.json"


class APIMode(StrEnum):
    LIVE = "Live Prices"
    OFFLINE = "Offline Cache"
    DISABLED = "Pricing Disabled"


data_obj = {
    "string": "Hello, World!",
    "integer": 42,
    "float": 123.456,
    "datetime": DateHelper.now(),
    "date": DateHelper.today(),
    "api_mode": APIMode.LIVE,
}


def test_write_json():
    """Test the JSONEncoder class writing to and reading from a JSON file."""
    # Save the to a JSON file
    file_path = Path(JSON_FILE)
    result = JSONEncoder.save_to_file(data_obj, file_path)
    assert result is True, "Failed to save data to JSON file"


def test_read_json():
    """Test the JSONEncoder class reading from a JSON file."""
    file_path = Path(JSON_FILE)
    loaded_data = JSONEncoder.read_from_file(file_path)
    assert isinstance(loaded_data, dict), "Loaded data should be a dictionary"
    assert loaded_data.get("string") == data_obj.get("string"), "String value mismatch"
    assert loaded_data.get("integer") == data_obj.get("integer"), "Integer value mismatch"
    assert loaded_data.get("float") == data_obj.get("float"), "Float value mismatch"
    assert loaded_data.get("datetime") == data_obj.get("datetime"), "Datetime value mismatch"
    assert loaded_data.get("date") == data_obj.get("date"), "Date value mismatch"
    assert loaded_data.get("api_mode") == data_obj.get("api_mode"), "API mode value mismatch"


def test_error_messages_include_cause(tmp_path: Path):
    """RuntimeErrors must carry the original error type, text and file path."""
    with pytest.raises(RuntimeError, match=r"TypeError.*not serializable") as exc_info:
        JSONEncoder.serialise_to_json({"bad": object()})
    assert isinstance(exc_info.value.__cause__, TypeError)

    with pytest.raises(RuntimeError, match=r"JSONDecodeError"):
        JSONEncoder.deserialise_from_json("{not json")

    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError) as exc_info:
        JSONEncoder.read_from_file(bad_file)
    assert str(bad_file) in str(exc_info.value)
    assert "JSONDecodeError" in str(exc_info.value)

    target = tmp_path / "out.json"
    with pytest.raises(RuntimeError) as exc_info:
        JSONEncoder.save_to_file({"bad": object()}, target)
    assert str(target) in str(exc_info.value)
    assert "TypeError" in str(exc_info.value)


def test_failed_save_leaves_no_temp_file_and_keeps_target(tmp_path: Path):
    """A failed save must not leave a stray temp file or touch the existing target."""
    target = tmp_path / "state.json"
    JSONEncoder.save_to_file({"value": 1}, target)
    with pytest.raises(RuntimeError):
        JSONEncoder.save_to_file({"bad": object()}, target)
    assert JSONEncoder.read_from_file(target) == {"value": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_successful_save_leaves_no_temp_file(tmp_path: Path):
    """After a successful save only the target file remains."""
    target = tmp_path / "state.json"
    assert JSONEncoder.save_to_file({"value": 1}, target) is True
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_save_non_ascii_round_trip(tmp_path: Path):
    """Non-ASCII text round-trips (json.dump uses ensure_ascii, so the latin-1 fallback is rarely hit)."""
    target = tmp_path / "latin.json"
    assert JSONEncoder.save_to_file({"text": "café"}, target) is True
    assert JSONEncoder.read_from_file(target) == {"text": "café"}
    assert [p.name for p in tmp_path.iterdir()] == ["latin.json"]


def test_save_preserves_file_mode(tmp_path: Path):
    """Replacing an existing file keeps its permissions; new files are 0644."""
    target = tmp_path / "state.json"
    JSONEncoder.save_to_file({"value": 1}, target)
    assert target.stat().st_mode & 0o777 == 0o644
    target.chmod(0o660)
    JSONEncoder.save_to_file({"value": 2}, target)
    assert target.stat().st_mode & 0o777 == 0o660


def test_concurrent_saves_same_path(tmp_path: Path):
    """Several threads saving to the same path all succeed and leave valid JSON."""
    target = tmp_path / "state.json"
    payloads = [{"writer": i, "items": list(range(500))} for i in range(8)]

    for _ in range(25):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda d: JSONEncoder.save_to_file(d, target), payloads))
        assert all(results)
        loaded = JSONEncoder.read_from_file(target)
        assert loaded in payloads
        assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
