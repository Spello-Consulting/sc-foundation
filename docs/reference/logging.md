# Logging

## Reading and tailing the log file

`SCLogger.read_logfile()` returns the full contents of the log file, and `SCLogger.read_logfile_since()` returns only
the content written since a previous call - the equivalent of `tail -f`. Both read the file while holding the logger's
logfile lock, so they never see a partially completed trim.

Each call to `read_logfile_since()` returns a `LogChunk`. Pass its `generation` and `offset` back on the next call. If
the log file has been trimmed (see `trim_logfile()`), truncated or replaced since the previous call, the chunk has
`reset=True` and contains the whole file, so the caller should replace what it holds rather than append:

```python
chunk = logger.read_logfile_since()
content = chunk.text

# ... later, e.g. polled every second by a web page
chunk = logger.read_logfile_since(chunk.generation, chunk.offset)
content = chunk.text if chunk.reset else content + chunk.text
```

::: sc_foundation.sc_logging.SCLogger

::: sc_foundation.sc_logging.LogChunk
