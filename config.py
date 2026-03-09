import dataclasses
import os
import sys
import tomllib
from pathlib import Path
from typing import Union, get_args, get_origin, get_type_hints

from schema import WAIConfigRoot

CONFIG_ENV_PREFIX = "WAI_"
CONFIG_FILE = os.getenv("WAI_CONFIG_FILE", "./conf/wai.toml")

# USE:
# from config import Config

# config = Config()
# config = Config("/path/to/config.toml")


class ConfigNode:
    def __init__(self, data: dict):
        self.__dict__["_data"] = {}

        for _key, _item in data.items():
            if isinstance(_item, dict):
                self._data[_key] = ConfigNode(_item)
            else:
                self._data[_key] = _item

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    # def __repr__(self):
    #     return f"ConfigNode({self._data})"


class Config:
    _instance = None

    def __new__(cls, path=CONFIG_FILE, schema=WAIConfigRoot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init(path, schema)
        return cls._instance

    def _init(self, path, schema):
        self.path = Path(path) if Path(path).is_absolute() else Path(Path.cwd() / path)
        self.schema = schema
        self.reload()

    def reload(self):
        def _write_toml(path: Path | None, data: dict, parent=""):
            lines = []

            for key, value in data.items():
                if isinstance(value, dict):
                    section = f"{parent}.{key}" if parent else key
                    lines.append(f"\n[{section}]")
                    lines.extend(_write_toml(None, value, section))
                else:
                    if isinstance(value, str):
                        value = f'"{value}"'
                    elif isinstance(value, bool):
                        value = str(value).lower()
                    lines.append(f"{key} = {value}")

            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w") as f:
                    f.write("\n".join(lines))

            return lines

        def _resolve_optional(t):
            if get_origin(t) is Union:
                args = [a for a in get_args(t) if a is not type(None)]
                if len(args) == 1:
                    return args[0]
            return t

        def _apply_env_overrides():
            def _parse_env(v):
                if v.lower() in ("true", "false"):
                    return v.lower() == "true"
                try:
                    return int(v)
                except ValueError:
                    pass
                try:
                    return float(v)
                except ValueError:
                    return v

            for env, value in os.environ.items():
                if not env.startswith(CONFIG_ENV_PREFIX):
                    continue

                _len = len(CONFIG_ENV_PREFIX)
                keypath = env[_len:].lower().split("__")
                ref = data

                for key in keypath[:-1]:
                    ref = ref.setdefault(key, {})

                ref[keypath[-1]] = _parse_env(value)

        def _apply_schema():
            hints = get_type_hints(self.schema)
            kwargs = {}

            for field in dataclasses.fields(self.schema):
                field_type = _resolve_optional(hints[field.name])
                value = data.get(field.name)

                if value is None:
                    kwargs[field.name] = None
                    continue

                if isinstance(value, dict):
                    kwargs[field.name] = field_type(**value)
                else:
                    kwargs[field.name] = value

            return self.schema(**kwargs)

        def _dataclass_to_dict(schema):
            """Create dict with default values from dataclass schema."""
            result = {}

            for f in dataclasses.fields(schema):
                t = _resolve_optional(f.type)

                if dataclasses.is_dataclass(t):
                    result[f.name] = _dataclass_to_dict(t)
                    continue

                if f.default is not dataclasses.MISSING:
                    result[f.name] = f.default
                else:
                    # required field without default
                    result[f.name] = "# REQUIRED FIELD"

            return result

        try:
            print(f"\nLooking at config file: {self.path}\n")
            with open(self.path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            print("Config not found.")

            _def_file = f"{self.path}.defaults"
            if Path(_def_file).exists():
                print(
                    f"\n{_def_file} exists, use it to create a corrected config file.\n"
                )
            else:
                print(
                    "- Generating defaults file:\n"
                    f" {_def_file}\n"
                    "Use it to create a corrected config file.\n"
                )
                default_data = _dataclass_to_dict(self.schema)
                _write_toml(Path(_def_file), default_data)
            sys.exit(0)

        _apply_env_overrides()

        if self.schema:
            self.data = _apply_schema()
        else:
            self.data = ConfigNode(data)

    def __getattr__(self, item):
        return getattr(self.data, item)
