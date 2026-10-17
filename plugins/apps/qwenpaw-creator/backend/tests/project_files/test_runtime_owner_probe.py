# -*- coding: utf-8 -*-
"""Tests for the advisory second-backend probe in ``facade``.

``_warn_on_second_backend`` reads ``runtime-owner.json`` and probes the
recorded pid with ``os.kill(pid, 0)``.  On Windows CPython a stale pid can
raise ``SystemError`` (WinError 6, "invalid handle") instead of ``OSError``
(#8194); the probe must treat that as "peer not alive" rather than letting
the startup hook abort.
"""
# pylint: disable=protected-access
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from services.project_files.facade import _warn_on_second_backend


def _write_marker(root: Path, pid: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "runtime-owner.json").write_text(
        json.dumps({"pid": pid, "startedAtEpoch": 123.0}),
        encoding="utf-8",
    )


def test_system_error_probe_reads_as_peer_not_alive(tmp_path, monkeypatch):
    """WinError 6 surfaces as SystemError, not OSError, on Windows."""
    _write_marker(tmp_path, 2924)

    def _raise_system_error(pid: int, sig: int) -> None:
        raise SystemError(
            "<class 'OSError'> returned a result with an exception set",
        )

    monkeypatch.setattr(os, "kill", _raise_system_error)

    assert _warn_on_second_backend(tmp_path) is False


def test_os_error_probe_reads_as_peer_not_alive(tmp_path, monkeypatch):
    """ProcessLookupError (OSError subclass) — pre-existing behavior."""
    _write_marker(tmp_path, 2924)

    def _raise_process_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError()

    monkeypatch.setattr(os, "kill", _raise_process_lookup)

    assert _warn_on_second_backend(tmp_path) is False


def test_live_peer_reports_alive_and_rewrites_marker(tmp_path, monkeypatch):
    _write_marker(tmp_path, 2924)

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    assert _warn_on_second_backend(tmp_path) is True
    rewritten = json.loads(
        (tmp_path / "runtime-owner.json").read_text(encoding="utf-8"),
    )
    assert rewritten["pid"] == os.getpid()


def test_own_pid_and_bad_markers_read_as_no_peer(tmp_path):
    # Our own pid: no probe, not a peer.
    _write_marker(tmp_path, os.getpid())
    assert _warn_on_second_backend(tmp_path) is False

    # Missing marker.
    assert _warn_on_second_backend(tmp_path / "absent") is False

    # Corrupt marker.
    (tmp_path / "runtime-owner.json").write_text("{nope", encoding="utf-8")
    assert _warn_on_second_backend(tmp_path) is False
