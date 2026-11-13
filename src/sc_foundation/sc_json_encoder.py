"""Take any object and serialises it to a json file, converting data types as needed and adding hints to allow the original object to be recreated."""
import copy
import datetime as dt
import enum
import importlib
import json
import os
import re
import tempfile
from pathlib import Path

from dateutil.parser import parse


class JSONEncoder:
    """Class to handle encoding and decoding of JSON data with special handling for datetime objects and enumerations."""
    @staticmethod
    def ready_dict_for_json(data: object) -> object:
        """Prepares a dict or list for JSON serialization.

        Args:
            data (object): The data to prepare.

        Raises:
            RuntimeError: If the data cannot be prepared.

        Returns:
            object: A dict or list ready for export to JSON.
        """
        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert(item) for item in obj]
            # Use the same logic as _encode_object for special types
            try:
                return JSONEncoder._encode_object(obj)
            except TypeError:
                return obj

        try:
            save_data = copy.deepcopy(data)
            save_data = JSONEncoder._add_datatype_hints(save_data)
        except (TypeError, ValueError) as e:
            msg = f"Failed to prepare data for JSON: {type(e).__name__}: {e}"
            raise RuntimeError(msg) from e
        return convert(save_data)

    @staticmethod
    def serialise_to_json(data) -> str:
        """Serialises the data to a JSON string, converting as needed.

        Args:
            data (object): The data to prepare.

        Raises:
            RuntimeError: If the data cannot be serialized.

        Returns:
            str: The JSON string representation of the data.
        """
        try:
            save_data = copy.deepcopy(data)
            save_data = JSONEncoder._add_datatype_hints(save_data)
            json_string = json.dumps(save_data, indent=4, default=JSONEncoder._encode_object)
        except (TypeError, ValueError) as e:
            msg = f"Failed to serialise data to JSON: {type(e).__name__}: {e}"
            raise RuntimeError(msg) from e
        else:
            return json_string

    @staticmethod
    def deserialise_from_json(json_string: str):
        """Deserialises the JSON string to an object, converting as needed.

        Args:
            json_string (str): The JSON string to deserialise.

        Raises:
            RuntimeError: If the data cannot be deserialized.

        Returns:
            return_data(object): The deserialized object.
        """
        try:
            json_data = json.loads(json_string)
            return_data = JSONEncoder.decode_object(json_data)
        except (json.JSONDecodeError, ValueError) as e:
            msg = f"Failed to deserialise JSON string: {type(e).__name__}: {e}"
            raise RuntimeError(msg) from e
        else:
            return return_data

    @staticmethod
    def save_to_file(data, file_path: Path) -> bool:
        """Saves the date to a JSON file, converting as needed.

        Args:
            data (object): The data to prepare.
            file_path (Path): The path to the JSON file to be created.

        Raises:
            RuntimeError: If the data cannot be serialized.

        Returns:
            result (bool): True if the pricing data was saved, False if not.
        """
        # Make sure the parent folder exists before trying to write the file
        file_path.parent.mkdir(parents=True, exist_ok=True)     # Issue 27
        temporary_path: Path | None = None
        try:
            save_data = copy.deepcopy(data)
            save_data = JSONEncoder._add_datatype_hints(save_data)

            # Write to a unique temp file in the target directory so concurrent writers never share a
            # temp file, and replace() remains an atomic rename on the same filesystem.
            fd, temporary_name = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp")
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as json_file:
                    json.dump(save_data, json_file, indent=4, default=JSONEncoder._encode_object)
                    json_file.flush()
                    os.fsync(json_file.fileno())
            except UnicodeEncodeError:
                # fd is already closed by the with block; reopen the same temp file (truncating it)
                with temporary_path.open("w", encoding="latin-1") as json_file:
                    json.dump(save_data, json_file, indent=4, default=JSONEncoder._encode_object)
                    json_file.flush()
                    os.fsync(json_file.fileno())

            # mkstemp creates the file as 0600; keep the existing file's mode, or use a normal default.
            try:
                mode = file_path.stat().st_mode & 0o777
            except FileNotFoundError:
                mode = 0o644
            temporary_path.chmod(mode)

            temporary_path.replace(file_path)
        except (TypeError, ValueError, OSError) as e:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            msg = f"Failed to save JSON to {file_path}: {type(e).__name__}: {e}"
            raise RuntimeError(msg) from e
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        return True

    @staticmethod
    def read_from_file(file_path: Path) -> object | None:
        """Reads the JSON data from a file and decodes it.

        Args:
            file_path (Path): The path to the JSON file.

        Raises:
            RuntimeError: If the data cannot be read or decoded.

        Returns:
            dict: The decoded JSON data or None if the file does not exist.
        """
        if not file_path.exists():
            return None

        try:
            try:
                with file_path.open("r", encoding="utf-8") as json_file:
                    json_data = json.load(json_file)
                    return_data = JSONEncoder.decode_object(json_data)
                    return return_data
            except UnicodeDecodeError:
                with file_path.open("r", encoding="latin-1") as json_file:
                    json_data = json.load(json_file)
                    return_data = JSONEncoder.decode_object(json_data)
                    return return_data
        except (json.JSONDecodeError, OSError) as e:
            msg = f"Failed to read JSON from {file_path}: {type(e).__name__}: {e}"
            raise RuntimeError(msg) from e

    @staticmethod
    def _add_datatype_hints(obj):
        """Add datetime hints to the object before it's serialized.

        Args:
            obj: The object to convert.

        Returns:
            The object with hints added
        """
        if isinstance(obj, dict):
            # Build a new dict so we can place hint-keys immediately after their associated key
            new_obj: dict = {}
            for k, v in obj.items():
                # Recurse for nested containers first
                if isinstance(v, (dict, list)):
                    v_conv = JSONEncoder._add_datatype_hints(v)
                else:
                    v_conv = v

                # Add the original key/value
                new_obj[k] = v_conv

                # Immediately add any hint key right after
                if isinstance(v_conv, (dt.date, dt.datetime, dt.time)):
                    new_obj[f"{k}__datatype"] = type(v_conv).__name__  # e.g. "date", "datetime", "time"
                elif isinstance(v_conv, enum.Enum):
                    enum_cls = v_conv.__class__
                    new_obj[f"{k}__enum"] = f"{enum_cls.__module__}.{enum_cls.__name__}.{v_conv.name}"

            return new_obj
        if isinstance(obj, list):
            return [JSONEncoder._add_datatype_hints(item) for item in obj]
        return obj

    @staticmethod
    def _encode_object(obj):
        """Convert the object to JSON serialisable format if it's a date or datetime. This function is use by json.dump().

        Args:
            obj: The object to convert.

        Raises:
            TypeError: If the object is not serializable.

        Returns:
            The JSON serializable representation of the object.
        """
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            return obj.isoformat()
        if isinstance(obj, enum.Enum):
            # Store enum by its value; hint added in _add_datatype_hints enables reconstruction
            return obj.value
        error_msg = f"Type {type(obj)} not serializable"
        raise TypeError(error_msg)

    @staticmethod
    def decode_object(obj):  # noqa: PLR0912, PLR0915
        """Convert the object back to its original form, including date and datetime objects.

        Args:
            obj (obj): The object (list, dict, etc.) to convert.

        Returns:
            object (obj): The original object.
        """
        if isinstance(obj, dict):  # noqa: PLR1702
            for k, v in list(obj.items()):
                if isinstance(v, str):
                    # See if there's a enum hint for this key
                    enum_hint_key = f"{k}__enum"
                    enum_hint = obj.get(enum_hint_key)
                    obj.pop(enum_hint_key, None)  # remove the enum hint from the object
                    if enum_hint:
                        try:
                            if "." in enum_hint and enum_hint.count(".") >= 2:
                                # New format: module.class.key_name
                                parts = enum_hint.rsplit(".", 2)
                                module_name, class_name, key_name = parts
                                enum_module = importlib.import_module(module_name)
                                enum_cls = getattr(enum_module, class_name)
                                if issubclass(enum_cls, enum.Enum):
                                    obj[k] = getattr(enum_cls, key_name)
                                    continue
                            else:
                                # Old format: module.class (fallback)
                                module_name, class_name = enum_hint.rsplit(".", 1)
                                enum_module = importlib.import_module(module_name)
                                enum_cls = getattr(enum_module, class_name)
                                if issubclass(enum_cls, enum.Enum):
                                    obj[k] = enum_cls(v)
                                    continue
                        except Exception:  # noqa: BLE001, S110
                            # If reconstruction fails, leave as-is and fall through
                            pass

                    # See if there's a datatype hint for this key
                    datatype_hint_key = f"{k}__datatype"
                    datatype_hint = obj.get(datatype_hint_key)
                    obj.pop(datatype_hint_key, None)  # remove the datatype hint from the object
                    if datatype_hint == "date":
                        try:
                            obj[k] = dt.date.fromisoformat(v)
                            continue
                        except ValueError:
                            pass
                    elif datatype_hint == "datetime":
                        try:
                            obj[k] = dt.datetime.fromisoformat(v)
                            continue
                        except ValueError:
                            pass
                    elif datatype_hint == "time":
                        try:
                            obj[k] = dt.time.fromisoformat(v)
                            continue
                        except ValueError:
                            pass

                    # If the string is a date-only value like "YYYY-MM-DD", decode to a date
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                        try:
                            obj[k] = dt.date.fromisoformat(v)
                            continue
                        except ValueError:
                            # fall through to the full parse attempt
                            pass

                    # Only try to parse if the string contains date/time-like patterns
                    # This prevents parsing strings like "Sat,Sun,Tue" as dates
                    if re.search(r"\d", v) and re.search(r"[:/\-]", v):
                        try:
                            dt_obj = parse(v, fuzzy=False)
                            # If time part is zero, treat as date
                            if dt_obj.time() == dt.time(0, 0):
                                obj[k] = dt_obj.date()
                            else:
                                obj[k] = dt_obj
                        except (ValueError, TypeError):
                            pass    # Just ignore
                elif isinstance(v, (dict, list)):
                    obj[k] = JSONEncoder.decode_object(v)
        elif isinstance(obj, list):
            return [JSONEncoder.decode_object(item) for item in obj]
        return obj
