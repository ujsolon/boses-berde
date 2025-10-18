"""Logic for installing dependencies in Pyodide.

Mostly taken from https://github.com/pydantic/pydantic.run/blob/main/src/frontend/src/prepare_env.py
"""

from __future__ import annotations as _annotations

import importlib
import logging
import re
import sys
import traceback
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

import micropip
import pyodide_js
import tomllib
from pyodide.code import find_imports

__all__ = 'prepare_env', 'dump_json'


class File(TypedDict):
    name: str
    content: str
    active: bool


@dataclass
class Success:
    dependencies: list[str] | None
    kind: Literal['success'] = 'success'


@dataclass
class Error:
    message: str
    kind: Literal['error'] = 'error'


async def prepare_env(files: list[File]) -> Success | Error:
    sys.setrecursionlimit(400)

    cwd = Path.cwd()
    for file in files:
        (cwd / file['name']).write_text(file['content'])

    active: File | None = next((f for f in files if f['active']), None)

    dependencies: list[str] | None = None
    if active:
        python_code = active['content']
        dependencies = _find_pep723_dependencies(python_code)
        if dependencies is None:
            dependencies = await _find_import_dependencies(python_code)

    if dependencies:
        dependencies = _add_extra_dependencies(dependencies)

        with _micropip_logging() as logs_filename:
            try:
                await micropip.install(dependencies, keep_going=True)
                importlib.invalidate_caches()
            except Exception:
                with open(logs_filename) as f:
                    logs = f.read()
                return Error(message=f'{logs} {traceback.format_exc()}')

    return Success(dependencies=dependencies)


def dump_json(value: Any) -> str | None:
    from pydantic_core import to_json

    if value is None:
        return None
    if isinstance(value, str):
        return value
    else:
        return to_json(value, indent=2, fallback=_json_fallback).decode()


def _json_fallback(value: Any) -> Any:
    tp: Any = type(value)
    module = tp.__module__
    if module == 'numpy':
        if tp.__name__ in {'ndarray', 'matrix'}:
            return value.tolist()
        else:
            return value.item()
    elif module == 'pyodide.ffi':
        return value.to_py()
    else:
        return repr(value)


def _add_extra_dependencies(dependencies: list[str]) -> list[str]:
    """Add extra dependencies we know some packages need.

    Workaround for micropip not installing some required transitive dependencies.
    See https://github.com/pyodide/micropip/issues/204

    pygments seems to be required to get rich to work properly, ssl is required for FastAPI and HTTPX,
    pydantic_ai requires newest typing_extensions.
    """
    extras: list[str] = []
    for d in dependencies:
        if d.startswith(('logfire', 'rich')):
            extras.append('pygments')
        elif d.startswith(('fastapi', 'httpx', 'pydantic_ai')):
            extras.append('ssl')

        if d.startswith('pydantic_ai'):
            extras.append('typing_extensions>=4.12')

        if len(extras) == 3:
            break

    return dependencies + extras


@contextmanager
def _micropip_logging() -> Iterator[str]:
    from micropip import logging as micropip_logging

    micropip_logging.setup_logging()
    logger = logging.getLogger('micropip')
    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    file_name = 'micropip.log'
    handler = logging.FileHandler(file_name)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    try:
        yield file_name
    finally:
        logger.removeHandler(handler)


def _find_pep723_dependencies(code: str) -> list[str] | None:
    """Extract dependencies from a script with PEP 723 metadata."""
    metadata = _read_pep723_metadata(code)
    dependencies: list[str] | None = metadata.get('dependencies')
    if dependencies is None:
        return None
    else:
        assert isinstance(dependencies, list), 'dependencies must be a list'
        assert all(isinstance(dep, str) for dep in dependencies), 'dependencies must be a list of strings'
        return dependencies


def _read_pep723_metadata(code: str) -> dict[str, Any]:
    """Read PEP 723 script metadata.

    Copied from https://packaging.python.org/en/latest/specifications/inline-script-metadata/#reference-implementation
    """
    name = 'script'
    magic_comment_regex = r'(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$'
    matches = list(filter(lambda m: m.group('type') == name, re.finditer(magic_comment_regex, code)))
    if len(matches) > 1:
        raise ValueError(f'Multiple {name} blocks found')
    elif len(matches) == 1:
        content = ''.join(
            line[2:] if line.startswith('# ') else line[1:]
            for line in matches[0].group('content').splitlines(keepends=True)
        )
        return tomllib.loads(content)
    else:
        return {}


async def _find_import_dependencies(code: str) -> list[str] | None:
    """Find dependencies in imports."""
    try:
        imports: list[str] = find_imports(code)
    except SyntaxError:
        return None
    else:
        return list(_find_imports_to_install(imports))


TO_PACKAGE_NAME: dict[str, str] = pyodide_js._api._import_name_to_package_name.to_py()  # pyright: ignore[reportPrivateUsage]


def _find_imports_to_install(imports: list[str]) -> Iterable[str]:
    """Given a list of module names being imported, return packages that are not installed."""
    for module in imports:
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            if package_name := TO_PACKAGE_NAME.get(module):
                yield package_name
            elif '.' not in module:
                yield module
