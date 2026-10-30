import os
from pathlib import Path


def asset_root() -> Path:
    return Path(os.getenv("ASSET_ROOT", "assets")).resolve()


def image_output_dir(project_id: int, *parts: str) -> str:
    return str(asset_root() / "projects" / str(project_id) / "images" / Path(*parts))


def absolute_asset_path(path: str) -> str:
    return str(asset_root() / path)


def relative_asset_path(path: str) -> str:
    return Path(path).resolve().relative_to(asset_root()).as_posix()
