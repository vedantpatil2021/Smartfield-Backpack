import tomllib
from pathlib import Path


def load_config(path: str = "/app/config.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
