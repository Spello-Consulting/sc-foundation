"""pytest for the SCLogger log file read / tail methods."""
import threading
from pathlib import Path

import pytest

from sc_foundation import LogChunk, SCLogger


def make_logger(logfile: Path, max_lines: int = 1000) -> SCLogger:
    """Create a logger writing only to the given log file.

    Returns:
        A configured SCLogger.
    """
    return SCLogger({
        "logfile_name": str(logfile),
        "file_verbosity": "debug",
        "console_verbosity": "none",
        "max_lines": max_lines,
    })


def test_read_logfile_returns_contents(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    logger.log_message("first message", "summary")
    logger.log_message("second message", "error")

    text = logger.read_logfile()

    assert "first message" in text
    assert "ERROR: second message" in text
    assert text == (tmp_path / "app.log").read_text(encoding="utf-8")


def test_read_logfile_missing_file(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")

    assert not logger.read_logfile()


def test_read_logfile_file_logging_disabled():
    logger = SCLogger({"logfile_name": None, "console_verbosity": "none"})

    assert not logger.read_logfile()
    chunk = logger.read_logfile_since()
    assert chunk == LogChunk(text="", generation=chunk.generation, offset=0, reset=True)


def test_read_logfile_since_first_call_returns_everything(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    logger.log_message("line one", "summary")

    chunk = logger.read_logfile_since()

    assert chunk.reset is True
    assert "line one" in chunk.text
    assert chunk.offset == (tmp_path / "app.log").stat().st_size


def test_read_logfile_since_returns_only_new_content(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    logger.log_message("line one", "summary")
    first = logger.read_logfile_since()

    logger.log_message("line two", "summary")
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is False
    assert "line one" not in second.text
    assert "line two" in second.text
    assert first.text + second.text == logger.read_logfile()


def test_read_logfile_since_no_new_content(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    logger.log_message("line one", "summary")
    first = logger.read_logfile_since()

    second = logger.read_logfile_since(first.generation, first.offset)

    assert second == LogChunk(text="", generation=first.generation, offset=first.offset, reset=False)


def test_read_logfile_since_file_created_after_first_call(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    first = logger.read_logfile_since()
    assert not first.text

    logger.log_message("line one", "summary")
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is False
    assert "line one" in second.text


def test_trim_resets_reader_even_when_file_regrows(tmp_path: Path):
    """After a trim the caller must get a reset, even if the file has since grown past its old offset."""
    logger = make_logger(tmp_path / "app.log", max_lines=5)
    for i in range(8):
        logger.log_message(f"before trim {i}", "summary")
    first = logger.read_logfile_since()

    logger.trim_logfile()
    for i in range(20):
        logger.log_message(f"after trim {i}", "summary")
    assert (tmp_path / "app.log").stat().st_size > first.offset

    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is True
    assert second.generation != first.generation
    assert second.text == logger.read_logfile()


def test_trim_without_rewrite_keeps_generation(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log", max_lines=100)
    logger.log_message("line one", "summary")
    first = logger.read_logfile_since()

    logger.trim_logfile()  # Under max_lines, so the file is not rewritten
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is False
    assert second.generation == first.generation


def test_external_truncation_resets_reader(tmp_path: Path):
    logfile = tmp_path / "app.log"
    logger = make_logger(logfile)
    logger.log_message("a fairly long line of text", "summary")
    first = logger.read_logfile_since()

    logfile.write_text("short\n", encoding="utf-8")
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is True
    assert second.text == "short\n"


def test_logfile_path_change_resets_reader(tmp_path: Path):
    logger = make_logger(tmp_path / "one.log")
    logger.log_message("in log one", "summary")
    first = logger.read_logfile_since()

    logger.initialise_settings({"logfile_name": str(tmp_path / "two.log"), "file_verbosity": "debug", "console_verbosity": "none"})
    logger.log_message("in log two", "summary")
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is True
    assert "in log one" not in second.text
    assert "in log two" in second.text


def test_same_logfile_path_keeps_generation(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")
    logger.log_message("line one", "summary")
    first = logger.read_logfile_since()

    logger.initialise_settings({"logfile_name": str(tmp_path / "app.log"), "file_verbosity": "debug", "console_verbosity": "none"})
    second = logger.read_logfile_since(first.generation, first.offset)

    assert second.reset is False


def test_reset_on_large_file_returns_tail_from_line_boundary(tmp_path: Path):
    logfile = tmp_path / "app.log"
    logger = make_logger(logfile, max_lines=0)
    for i in range(100):
        logger.log_message(f"message number {i:03d}", "summary")
    size = logfile.stat().st_size

    chunk = logger.read_logfile_since(max_bytes=200)

    assert chunk.reset is True
    assert chunk.offset == size
    assert chunk.text
    assert len(chunk.text.encode()) <= 200
    assert chunk.text.endswith("message number 099\n")
    assert logger.read_logfile().endswith(chunk.text)
    # Starts on a complete line
    assert set(chunk.text.splitlines()) <= set(logger.read_logfile().splitlines())


def test_incremental_read_is_split_on_line_boundaries(tmp_path: Path):
    logfile = tmp_path / "app.log"
    logger = make_logger(logfile, max_lines=0)
    logger.log_message("start", "summary")
    chunk = logger.read_logfile_since()
    text = chunk.text
    for i in range(50):
        logger.log_message(f"message number {i:03d} éè", "summary")

    reads = 0
    while True:
        chunk = logger.read_logfile_since(chunk.generation, chunk.offset, max_bytes=100)
        assert chunk.reset is False
        if not chunk.text:
            break
        assert chunk.text.endswith("\n")
        text += chunk.text
        reads += 1

    assert reads > 1
    assert text == logger.read_logfile()


def test_read_logfile_since_invalid_max_bytes(tmp_path: Path):
    logger = make_logger(tmp_path / "app.log")

    with pytest.raises(ValueError, match="max_bytes"):
        logger.read_logfile_since(max_bytes=0)


def test_concurrent_writes_and_trims_are_consistent(tmp_path: Path):
    """A tailing reader never sees a torn line while other threads write and trim."""
    logger = make_logger(tmp_path / "app.log", max_lines=20)
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            logger.log_message(f"concurrent message {i:06d}", "summary")
            i += 1
            if i % 25 == 0:
                logger.trim_logfile()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        chunk = logger.read_logfile_since()
        for _ in range(200):
            chunk = logger.read_logfile_since(chunk.generation, chunk.offset)
            for line in chunk.text.splitlines():
                assert "concurrent message " in line
                assert len(line.rsplit(" ", 1)[1]) == 6
    finally:
        stop.set()
        thread.join()
