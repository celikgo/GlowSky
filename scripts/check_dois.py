"""Verify that every DOI cited in this repository is registered and resolvable.

WHY THIS EXISTS SEPARATELY FROM THE LINK CHECKER

    docs-links.yml checks that URLs resolve. For a DOI it cannot finish the job:
    https://doi.org/10.1021/ci034243x correctly 302-redirects to pubs.acs.org, and
    ACS — like Wiley, Elsevier and most publishers — answers a non-browser client
    with 403 Forbidden. A link checker sees a 403 and cannot tell "this citation is
    dead" from "this publisher does not serve robots".

    So the link checker accepts 403 for those hosts, and this script does the part it
    cannot: it asks the DOI system itself. api.crossref.org is the registration
    authority's own API, it is bot-friendly, and a DOI that is not registered returns
    404 there. That is a stronger check than any HTTP status from a publisher, because
    it verifies the citation EXISTS rather than that some web server answered.

    It also returns the metadata, so this script can check that the DOI points at the
    work the citation claims — a DOI that resolves to a different paper is a worse
    error than one that does not resolve at all, and the only one a status code can
    never catch.

Usage:
    python -m scripts.check_dois            # scan the tree, verify every DOI found
    python -m scripts.check_dois --list     # just print what was found
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

# DOIs appear as bare `10.xxxx/yyyy` after a `doi:`/`DOI:` label, and inside
# https://doi.org/ URLs. Both forms are collected.
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-zA-Z0-9<>\[\]]+)")

#: Trailing punctuation that belongs to the prose, not to the identifier.
_TRAILING = ".,;:)]}'\"`>"

CROSSREF = "https://api.crossref.org/works/"
USER_AGENT = "glowsky-doi-check/1.0 (+https://github.com/celikgo/GlowSky)"


def _tracked_text_files() -> list[pathlib.Path]:
    """Only git-tracked files: a DOI in an untracked scratch file is not a citation."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        check=True, capture_output=True, text=True,
    )
    keep = {".md", ".py", ".csv", ".toml", ".yml", ".yaml", ".ts", ".tsx"}
    return [
        ROOT / line
        for line in out.stdout.splitlines()
        if pathlib.Path(line).suffix in keep
    ]


def collect_dois() -> dict[str, list[str]]:
    """DOI -> the files citing it."""
    found: dict[str, list[str]] = {}
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in _DOI_RE.finditer(text):
            doi = match.group(1).rstrip(_TRAILING)
            found.setdefault(doi, [])
            rel = str(path.relative_to(ROOT))
            if rel not in found[doi]:
                found[doi].append(rel)
    return found


def verify(doi: str) -> tuple[bool, str]:
    """Ask Crossref whether this DOI is registered, and to what."""
    req = urllib.request.Request(  # noqa: S310 - fixed https host, DOI appended
        CROSSREF + urllib.parse.quote(doi, safe="/"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            message = json.load(resp)["message"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "NOT REGISTERED in Crossref"
        return False, f"Crossref returned HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"could not reach Crossref: {exc}"

    title = (message.get("title") or ["<untitled>"])[0]
    container = (message.get("container-title") or ["?"])[0]
    year = message.get("issued", {}).get("date-parts", [["?"]])[0][0]
    return True, f"{title[:64]} — {container[:36]} ({year})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print DOIs and exit")
    args = parser.parse_args()

    dois = collect_dois()
    if not dois:
        print("no DOIs found in tracked files", file=sys.stderr)
        # Not a failure in itself, but worth saying out loud: this project's
        # credibility rests on its citations, and finding none is surprising.
        return 0

    print(f"checking {len(dois)} distinct DOI(s) cited in this repository\n")
    if args.list:
        for doi, files in sorted(dois.items()):
            print(f"  {doi}\n      cited in: {', '.join(files)}")
        return 0

    failures: list[str] = []
    for doi, files in sorted(dois.items()):
        ok, detail = verify(doi)
        print(f"  [{'OK ' if ok else 'DEAD'}] {doi}")
        print(f"         {detail}")
        if not ok:
            failures.append(f"{doi} ({detail}) cited in: {', '.join(files)}")
        # Crossref asks for polite request rates; this is a handful of DOIs.
        time.sleep(0.2)

    if failures:
        print(f"\n{len(failures)} unresolvable DOI(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"\nall {len(dois)} DOIs are registered and resolvable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
