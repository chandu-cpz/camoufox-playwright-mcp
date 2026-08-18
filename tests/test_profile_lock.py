from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from camoufox_playwright_mcp.backend.browser_backend import (
    _any_process_references_profile,
    _clear_stale_profile_locks,
    _is_profile_locked,
    _pid_alive,
)


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    return tmp_path / "browser-profile"


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


def _symlink_lock(path: Path, target: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)
    return path


class TestPidAlive:
    def test_self_pid_is_alive(self) -> None:
        assert _pid_alive(os.getpid()) is True

    def test_dead_pid_is_not_alive(self) -> None:
        assert _pid_alive(999_999_999) is False


class TestParentLockDetection:
    def test_empty_profile_is_not_locked(self, profile_dir: Path) -> None:
        assert _is_profile_locked(profile_dir) is False

    def test_live_singleton_lock_is_locked(self, profile_dir: Path) -> None:
        _symlink_lock(profile_dir / "SingletonLock", f"/tmp/host-{os.getpid()}")
        assert _is_profile_locked(profile_dir) is True

    def test_stale_singleton_lock_is_not_locked(self, profile_dir: Path) -> None:
        _symlink_lock(profile_dir / "SingletonLock", "/tmp/host-999999999")
        assert _is_profile_locked(profile_dir) is False

    @patch(
        "camoufox_playwright_mcp.backend.browser_backend._any_process_references_profile",
        return_value=True,
    )
    def test_parentlock_with_live_owner_is_locked(self, _mock: object, profile_dir: Path) -> None:
        _touch(profile_dir / ".parentlock")
        assert _is_profile_locked(profile_dir) is True

    @patch(
        "camoufox_playwright_mcp.backend.browser_backend._any_process_references_profile",
        return_value=False,
    )
    def test_parentlock_without_live_owner_is_not_locked(self, _mock: object, profile_dir: Path) -> None:
        _touch(profile_dir / ".parentlock")
        assert _is_profile_locked(profile_dir) is False

    @patch(
        "camoufox_playwright_mcp.backend.browser_backend._any_process_references_profile",
        return_value=True,
    )
    def test_singleton_lock_wins_over_absent_parentlock(self, _mock: object, profile_dir: Path) -> None:
        assert _is_profile_locked(profile_dir) is False


class TestProfileReferenceScan:
    def test_own_process_cmdline_does_not_match_itself(self, profile_dir: Path) -> None:
        assert _any_process_references_profile(profile_dir) is False

    def test_live_process_with_profile_path_is_detected(self, profile_dir: Path) -> None:
        import subprocess
        import sys

        marker = f"--profile={profile_dir}"
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)", marker]
        )
        try:
            assert _any_process_references_profile(profile_dir) is True
        finally:
            proc.kill()
            proc.wait()


class TestClearStaleLocks:
    def test_removes_stale_parentlock(self, profile_dir: Path) -> None:
        lock = _touch(profile_dir / ".parentlock")
        with patch(
            "camoufox_playwright_mcp.backend.browser_backend._any_process_references_profile",
            return_value=False,
        ):
            _clear_stale_profile_locks(profile_dir)
        assert not lock.exists()

    def test_keeps_live_parentlock(self, profile_dir: Path) -> None:
        lock = _touch(profile_dir / ".parentlock")
        with patch(
            "camoufox_playwright_mcp.backend.browser_backend._any_process_references_profile",
            return_value=True,
        ):
            _clear_stale_profile_locks(profile_dir)
        assert lock.exists()

    def test_removes_stale_singleton_lock(self, profile_dir: Path) -> None:
        lock = _symlink_lock(profile_dir / "SingletonLock", "/tmp/host-999999999")
        _clear_stale_profile_locks(profile_dir)
        assert not lock.exists()
