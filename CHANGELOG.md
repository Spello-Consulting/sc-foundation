# Changelog

## 3.6.2

### Fixed

- `JSONEncoder`: the `RuntimeError`s raised by `ready_dict_for_json`, `serialise_to_json`,
  `deserialise_from_json`, `save_to_file` and `read_from_file` now carry a message with the original
  error type and text (and the file path where there is one). Previously `str(e)` was empty.
- `JSONEncoder.save_to_file` now writes through a unique temp file in the target directory
  (`tempfile.mkstemp`) instead of a fixed `<name>.tmp`. Concurrent saves to the same path no longer
  collide or risk installing a corrupt file; the temp file is removed on failure. The target's existing
  file mode is preserved (new files are created as `0644`). Last writer still wins, so callers that need
  ordering must still lock.
