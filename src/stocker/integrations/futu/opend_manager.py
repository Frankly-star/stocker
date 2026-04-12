"""OpenD process manager: auto-detect, auto-start, login-wait, health-check.

Provides:
- ``ensure_opend()`` — find locally installed OpenD, start if needed.
- ``start_opend()`` — launch the OpenD process in background.
- ``stop_opend()`` — terminate the managed OpenD process.
- ``is_opend_running()`` — check if OpenD is accepting connections.
- ``check_opend_login()`` — check if OpenD has a logged-in session.
- ``wait_for_login()`` — block until user logs in via OpenD GUI or Futu client.

Note: OpenD must be manually downloaded from https://openapi.futunn.com/
      This module only handles finding and starting it automatically.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Managed subprocess handle
_opend_process: subprocess.Popen | None = None

def _get_search_paths() -> list[str]:
    """Return common OpenD installation search paths for the current platform."""
    paths: list[str] = []

    if sys.platform == "win32":
        paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\FutuOpenD"),
            os.path.expandvars(r"%LOCALAPPDATA%\OpenD"),
            os.path.expandvars(r"%APPDATA%\FutuOpenD"),
            r"C:\Program Files\FutuOpenD",
            r"C:\Program Files (x86)\FutuOpenD",
            r"C:\FutuOpenD",
            os.path.expanduser(r"~\Desktop\FutuOpenD"),
            os.path.expanduser(r"~\Downloads\FutuOpenD"),
            os.path.expanduser(r"~\Downloads\OpenD"),
        ]
    elif sys.platform == "darwin":
        paths = [
            "/Applications/FutuOpenD.app/Contents/MacOS",
            "/Applications/OpenD.app/Contents/MacOS",
            os.path.expanduser("~/Applications/FutuOpenD.app/Contents/MacOS"),
            os.path.expanduser("~/Downloads/FutuOpenD"),
            os.path.expanduser("~/Downloads/OpenD"),
        ]
    else:  # Linux
        paths = [
            "/usr/local/bin",
            "/opt/FutuOpenD",
            "/opt/OpenD",
            os.path.expanduser("~/FutuOpenD"),
            os.path.expanduser("~/OpenD"),
            os.path.expanduser("~/Downloads/FutuOpenD"),
        ]

    # Always include project-local directory
    paths.append(str(Path("data/opend").resolve()))
    return paths


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_opend(
    host: str = "127.0.0.1",
    port: int = 11111,
    timeout: int = 30,
) -> bool:
    """Make sure OpenD is running and reachable.

    1. If port is already open -> assume OpenD is running, return True.
    2. Search for OpenD binary in common install locations + PATH.
    3. If found, start it and wait for port to become available.
    4. If not found, print install instructions and return False.

    Returns:
        True if OpenD is reachable at ``host:port`` within *timeout* seconds.
    """
    if is_opend_running(host, port):
        logger.info("OpenD already running at %s:%d", host, port)
        return True

    # Search for binary
    binary = find_opend_binary()
    if binary is None:
        _print_install_instructions()
        return False

    logger.info("Found OpenD at: %s", binary)

    # Start process
    start_opend(binary, host=host, port=port)

    # Wait for port to become available
    return _wait_for_port(host, port, timeout=timeout)


def find_opend_binary() -> Path | None:
    """Search for the OpenD executable across common locations and PATH.

    Search order:
    1. Project-local ``data/opend/`` directory (recursive)
    2. Common platform-specific install paths
    3. System PATH (``shutil.which``)
    """
    import shutil as _shutil

    binary_names = _get_binary_names()

    search_paths = _get_search_paths()

    # 1. Search common paths (including data/opend/)
    for search_dir in search_paths:
        dirpath = Path(search_dir)
        if not dirpath.exists():
            continue

        for name in binary_names:
            # Direct file
            candidate = dirpath / name
            if candidate.is_file():
                return candidate

            # Recursive search (for nested extractions)
            try:
                for match in dirpath.rglob(name):
                    if match.is_file():
                        return match
            except (PermissionError, OSError):
                continue

    # 2. macOS .app bundle search
    if sys.platform == "darwin":
        for search_dir in search_paths:
            dirpath = Path(search_dir)
            if not dirpath.exists():
                continue
            try:
                for app_dir in dirpath.rglob("*.app"):
                    macos_bin = app_dir / "Contents" / "MacOS"
                    for name in binary_names:
                        candidate = macos_bin / name
                        if candidate.is_file():
                            return candidate
            except (PermissionError, OSError):
                continue

    # 3. System PATH
    for name in binary_names:
        found = _shutil.which(name)
        if found:
            return Path(found)

    return None


def start_opend(
    binary: Path,
    host: str = "127.0.0.1",
    port: int = 11111,
) -> None:
    """Launch OpenD as a background subprocess."""
    global _opend_process

    if _opend_process is not None and _opend_process.poll() is None:
        logger.info("OpenD process already running (pid=%d)", _opend_process.pid)
        return

    cmd = [str(binary)]
    cmd.extend([f"-api_ip={host}", f"-api_port={port}"])
    # Headless mode
    cmd.extend(["-no_monitor=1", "-console=0"])

    logger.info("Starting OpenD: %s", " ".join(cmd))

    try:
        if sys.platform == "win32":
            _opend_process = subprocess.Popen(
                cmd,
                cwd=str(binary.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            _opend_process = subprocess.Popen(
                cmd,
                cwd=str(binary.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        logger.info("OpenD process started (pid=%d)", _opend_process.pid)
    except Exception as e:
        logger.error("Failed to start OpenD: %s", e)
        _opend_process = None


def stop_opend() -> None:
    """Terminate the managed OpenD process."""
    global _opend_process

    if _opend_process is None:
        return

    if _opend_process.poll() is None:
        logger.info("Stopping OpenD (pid=%d)...", _opend_process.pid)
        _opend_process.terminate()
        try:
            _opend_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _opend_process.kill()
            logger.warning("OpenD process killed after timeout")
    _opend_process = None


def is_opend_running(host: str = "127.0.0.1", port: int = 11111) -> bool:
    """Check if OpenD is accepting TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def check_opend_login(host: str = "127.0.0.1", port: int = 11111) -> bool:
    """Check if OpenD has a logged-in session via get_global_state()."""
    try:
        from futu import OpenQuoteContext

        ctx = OpenQuoteContext(host=host, port=port)
        try:
            ret, data = ctx.get_global_state()
            if ret == 0 and data is not None:
                if hasattr(data, "iloc") and len(data) > 0:
                    row = data.iloc[0]
                    qot_ok = bool(row.get("qot_logined", False))
                    trd_ok = bool(row.get("trd_logined", False))
                    return qot_ok or trd_ok
                return True
            return False
        finally:
            ctx.close()
    except Exception as e:
        logger.debug("check_opend_login failed: %s", e)
        return False


def wait_for_login(
    host: str = "127.0.0.1",
    port: int = 11111,
    timeout: int = 300,
    poll_interval: int = 5,
) -> bool:
    """Wait for user to log in to OpenD.

    Prints a console banner with instructions, then polls until
    login is detected or timeout is reached.

    Returns:
        True if login was detected within the timeout.
    """
    # Quick check
    if check_opend_login(host, port):
        return True

    banner = f"""
================================================================================

   OpenD 已启动，但尚未登录富途账号。

   请完成以下任一操作：

     方式一：打开 FutuOpenD 可视化界面，输入账号密码登录
     方式二：打开富途牛牛客户端，登录后会自动同步到 OpenD

   等待登录中... (最长等待 {timeout} 秒)

================================================================================
"""
    print(banner)
    logger.info("Waiting for OpenD login at %s:%d (timeout=%ds)...", host, port, timeout)

    deadline = time.monotonic() + timeout
    dots = 0

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        dots += 1

        if check_opend_login(host, port):
            print("\n  [OK] OpenD 登录成功！正在继续启动...\n")
            logger.info("OpenD login detected")
            return True

        remaining = int(deadline - time.monotonic())
        marker = "." * (dots % 4 + 1)
        print(f"  等待登录中{marker:<4s} (剩余 {remaining}s)", end="\r", flush=True)

    print("\n  [TIMEOUT] 未检测到登录，系统将降级到内置模拟盘。\n")
    logger.warning("OpenD login wait timed out after %ds", timeout)
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_binary_names() -> list[str]:
    """Return possible OpenD binary names for the current platform."""
    if sys.platform == "win32":
        return ["FutuOpenD.exe", "OpenD.exe"]
    return ["FutuOpenD", "OpenD"]


def _wait_for_port(host: str, port: int, timeout: int = 30) -> bool:
    """Wait until a TCP port becomes connectable."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if is_opend_running(host, port):
            logger.info("OpenD is ready at %s:%d", host, port)
            return True
        time.sleep(1)

    logger.error("OpenD did not become ready within %ds at %s:%d", timeout, host, port)
    return False


def _print_install_instructions() -> None:
    """Print instructions for manually installing OpenD."""
    msg = """
================================================================================

   未找到 OpenD，请先手动安装：

   1. 访问 https://openapi.futunn.com/ 下载 OpenD
   2. 解压到以下任一位置（系统会自动检测）："""

    paths = _get_search_paths()
    for p in paths[:4]:
        msg += f"\n      - {p}"

    msg += """

   或者解压到项目目录下的 data/opend/

   安装完成后重新启动 Stocker 即可。

================================================================================
"""
    print(msg)
    logger.error("OpenD binary not found — see console for install instructions")
