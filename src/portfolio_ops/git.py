"""The git adapter (P11): the only place the engine runs git.

Only ``report`` needs the full history (spec §7.2). ``validate`` asks git where the
repository root is, what ``origin`` points at and what changed since the previous commit
(P1), and copes with the answer "there is no repository".
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Commit:
    sha: str
    date: dt.date  # the committer date, in UTC (§7.1)


@dataclass(frozen=True)
class Git:
    cwd: Path

    def _run(self, *args: str, stdin: bytes | None = None) -> bytes | None:
        """Run git; None when git is missing or the command fails."""
        try:
            result = subprocess.run(  # noqa: S603 — fixed argument list, no shell
                ["git", "-C", str(self.cwd), *args],  # noqa: S607 — git from PATH, by design
                input=stdin,
                capture_output=True,
                check=False,
            )
        except OSError:
            return None
        return result.stdout if result.returncode == 0 else None

    def _text(self, *args: str) -> str | None:
        out = self._run(*args)
        return out.decode("utf-8", "replace").strip() if out is not None else None

    def toplevel(self) -> Path | None:
        top = self._text("rev-parse", "--show-toplevel")
        return Path(top) if top else None

    def inside_work_tree(self) -> bool:
        return self._text("rev-parse", "--is-inside-work-tree") == "true"

    def is_shallow(self) -> bool:
        return self._text("rev-parse", "--is-shallow-repository") == "true"

    def prefix(self) -> str:
        """The path of ``cwd`` inside the repository, with a trailing slash, or ''."""
        return self._text("rev-parse", "--show-prefix") or ""

    def origin_url(self) -> str | None:
        return self._text("remote", "get-url", "origin") or None

    def revision(self, name: str) -> str | None:
        """The commit ``name`` resolves to, or None when this clone does not have it — the
        parent of a root commit, or of the oldest commit of a shallow clone."""
        return self._text("rev-parse", "--verify", "--quiet", f"{name}^{{commit}}") or None

    def commits_touching(self, pathspec: str, revisions: str | None = None) -> list[Commit]:
        """The commits in ``revisions`` — by default all of HEAD's history — that changed
        ``pathspec`` (relative to ``cwd``), newest first."""
        out = self._text(
            "log", "--format=%H %ct", *([revisions] if revisions else []), "--", pathspec
        )
        commits = []
        for line in (out or "").splitlines():
            sha, _, stamp = line.partition(" ")
            if sha and stamp.isdigit():
                commits.append(Commit(sha, _utc_date(int(stamp))))
        return commits

    def last_commit(self, *pathspecs: str) -> dt.date | None:
        """The committer date of the latest commit that touched ``pathspecs``."""
        out = self._text("log", "-1", "--format=%ct", "--", *pathspecs)
        return _utc_date(int(out)) if out and out.isdigit() else None

    def blobs(self, sha_paths: list[str]) -> list[bytes | None]:
        """Contents of ``<sha>:<path>`` objects in one ``git cat-file --batch`` call."""
        if not sha_paths:
            return []
        out = self._run("cat-file", "--batch", stdin="".join(f"{s}\n" for s in sha_paths).encode())
        if out is None:
            return [None] * len(sha_paths)
        blobs: list[bytes | None] = []
        position = 0
        for _ in sha_paths:
            end = out.index(b"\n", position)
            header = out[position:end].split()
            position = end + 1
            if len(header) == 3 and header[1] == b"blob":
                size = int(header[2])
                blobs.append(out[position : position + size])
                position += size + 1  # the object, then its trailing newline
            else:
                if len(header) == 3:  # an object that is not a blob: skip its content
                    position += int(header[2]) + 1
                blobs.append(None)
        return blobs


def _utc_date(timestamp: int) -> dt.date:
    return dt.datetime.fromtimestamp(timestamp, dt.UTC).date()
