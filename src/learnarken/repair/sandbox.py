"""Sandbox jail for the repair agent's code-execution tool (Day 7, Decision 6).

**Toy-scale (INV-7), stated honestly.** This is an *application-layer* fence:
an in-process AST/argv allow-list plus a temp-dir jail, resource rlimits, and a
subprocess timeout. It blocks the common footguns — path traversal, network,
disallowed imports/builtins/attributes, non-whitelisted shell, runaway
CPU/memory, symlink exfiltration — and every one is test-asserted. It is **not**
OS-level isolation: there is no namespace/seccomp, so a determined native
sandbox-escape could still break out. Production would run this inside
nsjail/gVisor/a container; that boundary is where a real jail belongs.

Hardened after the Day 7 red-team (docs/reviews/day7.md): the import allow-list
no longer includes `pathlib`/`sys`, file/network *methods* (`read_text`,
`write_text`, `parse`, …) are refused so an allowed import cannot do I/O, shell
*arguments* are jailed (no absolute/`..`/URL/output-flag), source symlinks are
refused on copy, and `RLIMIT_AS/CPU/FSIZE` are enforced.
"""

from __future__ import annotations

import ast
import difflib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from learnarken.loader import MAX_FILE_BYTES
from learnarken.repair.config import SandboxPolicy

# Builtins that defeat the import allow-list (escape hatches).
_FORBIDDEN_NAMES = frozenset(
    {
        "eval", "exec", "compile", "__import__", "open", "globals", "vars", "locals",
        "input", "breakpoint", "getattr", "setattr", "delattr", "memoryview",
    }
)  # fmt: skip
# Attribute names refused regardless of receiver: process/network primitives AND
# file I/O methods (so an allowed import like lxml/defusedxml cannot read or
# write files or fetch URLs — red-team #1).
_FORBIDDEN_ATTRS = frozenset(
    {
        "system", "popen", "spawn", "fork", "exec", "socket", "connect",
        "__globals__", "__builtins__", "__class__", "__bases__", "__subclasses__",
        "read_text", "write_text", "read_bytes", "write_bytes", "parse", "iterparse",
        "write", "unlink", "rename", "replace", "mkdir", "rmdir", "remove",
        "chmod", "symlink_to", "open", "load", "urlopen", "request",
    }
)  # fmt: skip
# Shell flags permitted on whitelisted commands (read-only, no output/recurse).
_SAFE_SHELL_FLAGS = frozenset({"--noout", "--nonet", "-n", "-c", "-i", "-l", "-w", "-H", "-h"})


class SandboxViolation(RuntimeError):
    """Static or path check refused the code/argument before it could run."""


@dataclass
class ExecResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int | None  # None when killed by the timeout


def _safe_basename(name: str) -> str:
    """A caller-supplied file reference must be a bare basename (no traversal)."""
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        raise SandboxViolation(f"unsafe file reference: {name!r}")
    return name


class Sandbox:
    """A per-run temp jail holding copies of one package's XML files."""

    def __init__(self, package_dir: str | Path, policy: SandboxPolicy) -> None:
        self.policy = policy
        self.source = Path(package_dir).resolve()
        self._tmp = tempfile.mkdtemp(prefix="learnarken-repair-")
        self.root = Path(self._tmp).resolve()
        # Bound the target-finding identity the code tools may touch (red-team
        # #4/#5): set by the agent before each finding; None ⇒ no patch allowed.
        self.target_key: str | None = None
        self.target_file: str | None = None
        for xml in sorted(self.source.glob("*.xml")):
            if xml.is_symlink():  # red-team #3 — never copy a symlink's target in
                raise SandboxViolation(f"refusing symlinked package file: {xml.name}")
            if xml.stat().st_size > MAX_FILE_BYTES:  # red-team #16 — skip oversized
                continue
            shutil.copy2(xml, self.root / xml.name)
        icn = self.source / "icn"
        if icn.is_dir() and not icn.is_symlink():
            (self.root / "icn").mkdir()
            for f in sorted(icn.iterdir()):
                if f.is_file() and not f.is_symlink():
                    shutil.copy2(f, self.root / "icn" / f.name)

    # -- lifecycle ---------------------------------------------------------
    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()

    # -- path jail ---------------------------------------------------------
    def resolve(self, name: str) -> Path:
        """Resolve a caller-supplied path and assert it stays inside the jail.

        Rejects absolute paths, `..` traversal, and symlink escapes — the
        resolved target must be a descendant of the jail root.
        """
        candidate = (self.root / name).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise SandboxViolation(f"path escapes the sandbox jail: {name!r}")
        return candidate

    def read(self, name: str) -> str:
        return self.resolve(name).read_text(encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        self.resolve(name).write_text(text, encoding="utf-8")

    def diff(self, name: str) -> str:
        """Unified diff of a jailed file against the pristine source copy."""
        _safe_basename(name)  # red-team #15 — jail the source side too
        before = (self.source / name).read_text(encoding="utf-8").splitlines(keepends=True)
        after = self.resolve(name).read_text(encoding="utf-8").splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(before, after, fromfile=f"a/{name}", tofile=f"b/{name}")
        )

    # -- code execution ----------------------------------------------------
    def exec_code(self, kind: str, code: str) -> ExecResult:
        if kind == "python":
            return self._exec_python(code)
        if kind == "shell":
            return self._exec_shell(code)
        raise SandboxViolation(f"unknown exec kind {kind!r} (python|shell)")

    def _assert_python_safe(self, code: str) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise SandboxViolation(f"python does not parse: {exc}") from exc
        allowed = set(self.policy.allowed_python_imports)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in allowed:
                        raise SandboxViolation(f"import not allowed: {alias.name!r}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] not in allowed:
                    raise SandboxViolation(f"import not allowed: from {node.module!r}")
            elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
                raise SandboxViolation(f"forbidden builtin: {node.id!r}")
            elif isinstance(node, ast.Attribute) and (
                node.attr in _FORBIDDEN_ATTRS or node.attr.startswith("__")
            ):
                raise SandboxViolation(f"forbidden attribute access: .{node.attr}")

    def _exec_python(self, code: str) -> ExecResult:
        self._assert_python_safe(code)
        # `-I` isolates the interpreter; cwd is the jail. No network/file I/O is
        # reachable: socket/urllib are un-importable and file methods are refused.
        return self._run([sys.executable, "-I", "-c", code])

    def _assert_shell_arg_safe(self, token: str) -> None:
        if "://" in token:
            raise SandboxViolation(f"URL argument refused: {token!r}")
        if token.startswith("-"):
            if token not in _SAFE_SHELL_FLAGS:
                raise SandboxViolation(f"shell flag not allowed: {token!r}")
            return
        if token.startswith("/") or ".." in token:
            raise SandboxViolation(f"path argument escapes the jail: {token!r}")
        if "/" in token:
            self.resolve(token)  # a relative subpath must resolve inside the jail

    def _exec_shell(self, command: str) -> ExecResult:
        argv = command.split()
        if not argv:
            raise SandboxViolation("empty shell command")
        if argv[0] not in self.policy.shell_whitelist:
            raise SandboxViolation(
                f"shell command not whitelisted: {argv[0]!r} "
                f"(allowed: {sorted(self.policy.shell_whitelist)})"
            )
        for token in argv:
            if any(ch in token for ch in ";|&`$><\n"):
                raise SandboxViolation(f"shell metacharacter refused in {token!r}")
        for token in argv[1:]:  # red-team #2 — jail every argument, not just argv[0]
            self._assert_shell_arg_safe(token)
        return self._run(argv)

    def _set_limits(self) -> None:  # pragma: no cover — runs in the forked child
        """preexec: cap address space, CPU seconds and file size (red-team #8)."""
        import contextlib
        import resource

        mem = self.policy.mem_mb * 1024 * 1024
        cpu = max(1, int(self.policy.timeout_s) + 1)
        for res, value in (
            (resource.RLIMIT_AS, mem),
            (resource.RLIMIT_CPU, cpu),
            (resource.RLIMIT_FSIZE, 16 * 1024 * 1024),
        ):
            # Some platforms (macOS RLIMIT_AS) refuse — best effort.
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(res, (value, value))

    def _run(self, argv: list[str]) -> ExecResult:
        try:
            proc = subprocess.run(  # noqa: S603 — argv list, no shell, jailed cwd
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.policy.timeout_s,
                env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "LC_ALL": "C"},
                check=False,
                preexec_fn=self._set_limits,
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout or ""
            return ExecResult(
                ok=False,
                stdout=out.decode("utf-8", "replace") if isinstance(out, bytes) else out,
                stderr=f"sandbox timeout after {self.policy.timeout_s}s (circuit-breaker)",
                exit_code=None,
            )
        return ExecResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout[:8000],
            stderr=proc.stderr[:2000],
            exit_code=proc.returncode,
        )
