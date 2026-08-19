"""The version appears in five places; they must agree.

A release tag that disagrees with the version inside the artifacts it ships is a
release nobody can reason about afterwards: a bug report saying "0.1.0" stops
identifying a build. There is no single source of truth available here — the Python
package, the desktop package, the Tauri bundle and the release compose file each need
the version in their own format — so the next best thing is a test that they never
drift apart.
"""
from __future__ import annotations

import json
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def _desktop_package_version() -> str:
    return json.loads((ROOT / "apps/desktop/package.json").read_text())["version"]


def _tauri_version() -> str:
    return json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text())["version"]


def _cargo_version() -> str:
    text = (ROOT / "apps/desktop/src-tauri/Cargo.toml").read_text()
    return tomllib.loads(text)["package"]["version"]


def _release_compose_version() -> str:
    """The image tag docker-compose.release.yml defaults to.

    Read with a regex rather than a YAML parser: the value is inside a
    `${GLOWSKY_VERSION:-0.1.0}` interpolation, which is a compose construct rather than
    a YAML one, so the tag is part of an opaque string either way.
    """
    text = (ROOT / "docker-compose.release.yml").read_text()
    tags = set(re.findall(r"ghcr\.io/celikgo/glowsky:\$\{GLOWSKY_VERSION:-([^}]+)\}", text))
    assert tags, "docker-compose.release.yml declares no default image tag"
    assert len(tags) == 1, (
        f"docker-compose.release.yml pins more than one default version: {sorted(tags)}. "
        f"The api, worker and migrate services must run the same image."
    )
    return tags.pop()


def test_all_version_declarations_agree():
    versions = {
        "pyproject.toml": _pyproject_version(),
        "apps/desktop/package.json": _desktop_package_version(),
        "apps/desktop/src-tauri/tauri.conf.json": _tauri_version(),
        "apps/desktop/src-tauri/Cargo.toml": _cargo_version(),
        "docker-compose.release.yml": _release_compose_version(),
    }
    distinct = set(versions.values())
    assert len(distinct) == 1, (
        f"version declarations disagree: {versions}. A release tag that disagrees with "
        f"the artifacts it ships makes every later bug report ambiguous."
    )


def test_the_version_is_a_plain_semver():
    """No 'v' prefix, no pre-release suffix in the files themselves.

    The tag carries the 'v' (v0.1.0); the files carry the bare version. Keeping the two
    conventions distinct is what lets release tooling map between them unambiguously.
    """
    version = _pyproject_version()
    assert _SEMVER.match(version), (
        f"version {version!r} is not a plain MAJOR.MINOR.PATCH; the 'v' prefix belongs "
        f"on the git tag, not in the files"
    )
