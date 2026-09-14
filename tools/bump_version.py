"""Bump the patch version, in both of the places that hold it.

The version lives in pyproject.toml (what PyPI sees) and in
src/iporigin/__init__.py (what `iporigin --version` and any caller sees).
Nothing enforces that they agree, and a release that bumps one of them
ships a package that lies about itself — so this refuses to touch either
unless they start out identical.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "iporigin" / "__init__.py"

PYPROJECT_RE = re.compile(r'^version = "([^"]+)"', re.M)
INIT_RE = re.compile(r'^__version__ = "([^"]+)"', re.M)


def read_versions(pyproject_text, init_text):
    """The declared version in each file, as a pair."""
    found = []
    for pattern, text, where in (
        (PYPROJECT_RE, pyproject_text, "pyproject.toml"),
        (INIT_RE, init_text, "__init__.py"),
    ):
        match = pattern.search(text)
        if not match:
            raise ValueError("no version declaration found in %s" % where)
        found.append(match.group(1))
    return tuple(found)


def next_patch(version):
    """1.1.0 -> 1.1.1. Refuses anything that is not three plain numbers,
    because guessing at what comes after 2.0.0rc1 is not this script's job."""
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(
            "%r is not a plain major.minor.patch version; bump it by hand" % version
        )
    major, minor, patch = parts
    return "%s.%s.%d" % (major, minor, int(patch) + 1)


def bump(pyproject_text, init_text):
    """Both files' new contents, plus the version they now declare."""
    current_pyproject, current_init = read_versions(pyproject_text, init_text)
    if current_pyproject != current_init:
        raise ValueError(
            "pyproject.toml says %s but __init__.py says %s; fix that before "
            "releasing" % (current_pyproject, current_init)
        )
    new = next_patch(current_pyproject)
    return (
        PYPROJECT_RE.sub('version = "%s"' % new, pyproject_text, count=1),
        INIT_RE.sub('__version__ = "%s"' % new, init_text, count=1),
        new,
    )


def main(argv):
    pyproject_text = PYPROJECT.read_text()
    init_text = INIT.read_text()

    if "--current" in argv:
        print(read_versions(pyproject_text, init_text)[0])
        return 0

    new_pyproject, new_init, new = bump(pyproject_text, init_text)
    if "--dry-run" not in argv:
        PYPROJECT.write_text(new_pyproject)
        INIT.write_text(new_init)
    print(new)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
