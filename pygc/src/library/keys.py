"""OpenSSH Ed25519 identity creation and public-key parsing."""

import base64
import os
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from .constants import PRIVATE_KEY_FILE


def public_key(value: str) -> str:
    """Accept the SSH wire encoding of exactly one 32-byte Ed25519 key."""
    parts = value.strip().split(maxsplit=2)
    if len(parts) < 2 or parts[0] != "ssh-ed25519" or len(value.strip().splitlines()) != 1:
        raise ValueError("Expected one OpenSSH Ed25519 public key")
    raw = base64.b64decode(parts[1], validate=True)
    prefix = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    if len(raw) != len(prefix) + 32 or not raw.startswith(prefix):
        raise ValueError("Invalid Ed25519 public key encoding")
    return value.strip()


def local_public_key() -> str:
    """Link a finished key atomically so concurrent initializers share the winner."""
    key = Path.home() / PRIVATE_KEY_FILE
    if not os.path.lexists(key):
        with TemporaryDirectory(dir=key.parent) as directory:
            candidate = Path(directory) / "identity"
            _keygen("-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(candidate))
            try:
                os.link(candidate, key)
            except FileExistsError:
                pass
    mode = key.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise OSError("Expected an owner-only regular Git-centric private key")
    return public_key(_keygen("-y", "-P", "", "-f", str(key)))


def _keygen(*args: str) -> str:
    result = subprocess.run(
        ["ssh-keygen", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    if result.returncode:
        raise OSError("ssh-keygen could not generate or read the Git-centric Ed25519 key")
    return result.stdout
