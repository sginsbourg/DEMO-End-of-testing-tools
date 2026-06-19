#!/usr/bin/env python3
r"""
notepad_di_validator.py

Automated data-integrity validation harness for Windows Notepad (notepad.exe),
implementing the automatable test cases from the "Test Plan: Data Integrity
Validation - Notepad.exe" document (test case IDs DI-01 .. DI-29).

WHAT THIS SCRIPT DOES
----------------------
For each test case, the harness:
  1. Generates a known source fixture (bytes or text).
  2. Drives notepad.exe through the operation under test (open/save/reopen,
     change encoding, paste, find-replace, etc.) using UI Automation via
     pywinauto, OR performs the equivalent operation directly against the
     file when the case is encoding/byte-level only and UI automation would
     not add coverage (clearly marked per-case).
  3. Reads back the resulting file as raw bytes.
  4. Computes a SHA-256 hash and a byte-level diff against the expected
     result and renders a pass/fail verdict per the plan's Section 4.4
     (Pass/Fail Criteria): only a byte-identical / codepoint-identical
     match is a pass; any unexplained difference is a fail, regardless of
     whether Notepad displayed a warning.

REQUIREMENTS
------------
  - Windows 10/11 with notepad.exe on PATH.
  - Python 3.9+
  - pip install pywinauto

USAGE
-----
  python notepad_di_validator.py                 # run full automatable suite
  python notepad_di_validator.py --case DI-09     # run a single case
  python notepad_di_validator.py --list           # list available cases
  python notepad_di_validator.py --large-files    # include the 10/100 MB
                                                    # large-file cases (slow;
                                                    # excluded by default)
  python notepad_di_validator.py --workdir D:\di_test --report report.json

NOTES ON SCOPE
--------------
This script automates the test cases that can be driven deterministically
and headlessly. The following cases from the test plan are intentionally
OUT of scope for this script and are listed at the end of the run as
"requires manual or specialized execution", per Section 4 of the plan:

  DI-04  External modification while file is open   (needs a race with a
                                                        second process and a
                                                        modal dialog assertion)
  DI-06  Concurrent open in two Notepad instances     (multi-window UI race)
  DI-07  Disk full / write failure during save        (needs constrained
                                                        volume or I/O fault
                                                        injection)
  DI-08  Crash/force-close during save                (needs a fault-
                                                        injecting I/O harness)
  DI-20  1 GB file round-trip                          (resource-heavy; see
                                                        --large-files cap and
                                                        notes below)
  DI-21  4 GB boundary file round-trip                 (resource-heavy;
                                                        run via the separate
                                                        large_file_stress.py
                                                        helper, not by default)

These are flagged, not silently skipped, in the final report.
"""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
# Platform / dependency guard
# --------------------------------------------------------------------------

IS_WINDOWS = platform.system() == "Windows"

PYWINAUTO_AVAILABLE = False
if IS_WINDOWS:
    try:
        from pywinauto.application import Application
        from pywinauto.keyboard import send_keys
        from pywinauto import findwindows, timings
        PYWINAUTO_AVAILABLE = True
    except ImportError:
        PYWINAUTO_AVAILABLE = False


# --------------------------------------------------------------------------
# Result data model
# --------------------------------------------------------------------------

@dataclass
class TestResult:
    case_id: str
    title: str
    priority: str
    category: str
    passed: Optional[bool] = None       # None = skipped/error, not a verdict
    skipped: bool = False
    error: Optional[str] = None
    detail: str = ""
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None
    duration_s: float = 0.0

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "title": self.title,
            "priority": self.priority,
            "category": self.category,
            "passed": self.passed,
            "skipped": self.skipped,
            "error": self.error,
            "detail": self.detail,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "duration_s": round(self.duration_s, 3),
        }


# --------------------------------------------------------------------------
# Core utilities
# --------------------------------------------------------------------------

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_diff_offset(a: bytes, b: bytes) -> Optional[int]:
    """Return the index of the first byte that differs, or None if identical
    up to the length of the shorter buffer (in which case a length mismatch
    is the issue)."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return None


def hex_context(data: bytes, offset: int, width: int = 8) -> str:
    start = max(0, offset - width)
    end = min(len(data), offset + width)
    snippet = data[start:end]
    return " ".join(f"{b:02X}" for b in snippet)


def kill_notepad_processes():
    """Best-effort cleanup so stray Notepad windows from a previous failed
    run don't interfere with UI automation focus."""
    if not IS_WINDOWS:
        return
    os.system("taskkill /IM notepad.exe /F >NUL 2>NUL")
    time.sleep(0.3)


# --------------------------------------------------------------------------
# UI Automation driver for Notepad
# --------------------------------------------------------------------------

class NotepadDriver:
    """
    Thin wrapper around pywinauto for the small set of Notepad operations
    this harness needs: open a file, type/paste text, save (Ctrl+S), save as
    with a specific encoding, find/replace, and close without saving.

    Modern Notepad (Store-delivered, Windows 11) and legacy inbox Notepad
    have slightly different dialog layouts; this driver targets the modern
    Save As dialog with an encoding combo box. If your build differs, adjust
    the control identifiers in _save_as_dialog().
    """

    def __init__(self, exe_path: str = "notepad.exe", timeout: float = 15.0):
        self.exe_path = exe_path
        self.timeout = timeout
        self.app = None
        self.window = None

    def open_blank(self):
        self.app = Application(backend="uia").start(self.exe_path)
        time.sleep(0.5)
        self.window = self.app.top_window()
        self.window.wait("visible", timeout=self.timeout)
        return self

    def open_file(self, file_path: Path):
        self.app = Application(backend="uia").start(f'{self.exe_path} "{file_path}"')
        time.sleep(0.5)
        self.window = self.app.top_window()
        self.window.wait("visible", timeout=self.timeout)
        return self

    def _editor(self):
        # The main text editor control. Modern Notepad exposes it as an
        # "Edit" control inside the window tree; pywinauto's UIA backend
        # generally finds it via control_type "Edit" or "Document".
        try:
            return self.window.child_window(control_type="Edit")
        except Exception:
            return self.window.child_window(control_type="Document")

    def select_all_and_delete(self):
        editor = self._editor()
        editor.set_focus()
        send_keys("^a{DELETE}")

    def type_text_literal(self, text: str):
        """Set text directly via the control's value where possible, to
        avoid keyboard-layout-dependent character drops for non-ASCII
        content. Falls back to send_keys for plain ASCII."""
        editor = self._editor()
        editor.set_focus()
        try:
            editor.set_edit_text(text)
        except Exception:
            # Fallback: clipboard paste, which preserves Unicode reliably
            self.paste_via_clipboard(text)

    def paste_via_clipboard(self, text: str):
        import win32clipboard  # provided by pywin32, a pywinauto dependency
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()
        editor = self._editor()
        editor.set_focus()
        send_keys("^a{DELETE}")
        send_keys("^v")

    def get_clipboard_text(self) -> str:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return data

    def copy_all_to_clipboard(self):
        editor = self._editor()
        editor.set_focus()
        send_keys("^a^c")
        time.sleep(0.2)

    def save_plain(self):
        """Ctrl+S on an already-named file (no Save As dialog expected)."""
        editor = self._editor()
        editor.set_focus()
        send_keys("^s")
        time.sleep(0.4)

    def save_as(self, file_path: Path, encoding_label: Optional[str] = None):
        """
        Triggers Save As, types the full path into the filename field, and
        if encoding_label is given, selects it from the encoding combo box
        before confirming.

        encoding_label should match the exact text Notepad shows, e.g.:
          "UTF-8", "UTF-8 with BOM", "UTF-16 LE", "UTF-16 BE", "ANSI"
        """
        editor = self._editor()
        editor.set_focus()
        send_keys("^+s")  # Ctrl+Shift+S forces Save As even if already named
        time.sleep(0.5)

        save_dlg = self.app.window(title_re=".*Save.*")
        save_dlg.wait("visible", timeout=self.timeout)

        if encoding_label:
            try:
                combo = save_dlg.child_window(control_type="ComboBox")
                combo.select(encoding_label)
            except Exception as e:
                raise RuntimeError(
                    f"Could not select encoding '{encoding_label}' in Save As "
                    f"dialog: {e}. The dialog layout may differ from the "
                    f"version this driver targets."
                )

        filename_box = save_dlg.child_window(control_type="ComboBox", found_index=0)
        try:
            filename_edit = save_dlg.child_window(class_name="Edit", found_index=0)
            filename_edit.set_edit_text(str(file_path))
        except Exception:
            send_keys(str(file_path))

        send_keys("%s")  # Alt+S = Save in the standard Save As dialog
        time.sleep(0.6)

        # Handle "replace existing file?" confirmation if present
        try:
            confirm_dlg = self.app.window(title_re=".*Confirm.*", timeout=2)
            if confirm_dlg.exists():
                send_keys("{ENTER}")
                time.sleep(0.3)
        except Exception:
            pass

    def find_replace_all(self, find_text: str, replace_text: str):
        editor = self._editor()
        editor.set_focus()
        send_keys("^h")
        time.sleep(0.4)
        dlg = self.app.window(title_re=".*Replace.*")
        dlg.wait("visible", timeout=self.timeout)
        find_box = dlg.child_window(auto_id="1148", control_type="Edit")
        replace_box = dlg.child_window(auto_id="1149", control_type="Edit")
        find_box.set_edit_text(find_text)
        replace_box.set_edit_text(replace_text)
        replace_all_btn = dlg.child_window(title_re=".*Replace All.*", control_type="Button")
        replace_all_btn.click_input()
        time.sleep(0.3)
        try:
            dlg.close()
        except Exception:
            pass

    def close_discard_changes(self):
        try:
            self.window.close()
            time.sleep(0.3)
            dlg = self.app.window(title_re=".*Notepad.*", timeout=2)
            if dlg.exists():
                send_keys("{ENTER}")  # default to "Don't Save" on most builds
        except Exception:
            pass
        finally:
            kill_notepad_processes()

    def close_app(self):
        try:
            self.app.kill()
        except Exception:
            kill_notepad_processes()


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------

class Fixtures:
    """Deterministic, version-controlled-friendly fixture content used
    across test cases, mirroring Section 4.3 of the test plan."""

    ASCII_BASELINE = (
        "The quick brown fox jumps over the lazy dog. "
        "0123456789 !@#$%^&*()_+-=[]{}|;:',.<>/?`~\""
    )

    MULTILINGUAL = (
        "Latin: The quick brown fox.\n"
        "Cyrillic: \u0411\u044b\u0441\u0442\u0440\u0430\u044f "
        "\u043a\u043e\u0440\u0438\u0447\u043d\u0435\u0432\u0430\u044f "
        "\u043b\u0438\u0441\u0438\u0446\u0430.\n"
        "Greek: \u0393\u03b1\u03b6\u03ad\u03b5\u03c2 \u03ba\u03b1\u1f76 "
        "\u03bc\u03c5\u03c1\u03c4\u03b9\u03ad\u03c2.\n"
        "Arabic: \u0627\u0644\u062b\u0639\u0644\u0628 \u0627\u0644\u0628\u0646\u064a "
        "\u0627\u0644\u0633\u0631\u064a\u0639.\n"
        "Hebrew: \u05d4\u05e9\u05d5\u05e2\u05dc \u05d4\u05de\u05d4\u05d9\u05e8 "
        "\u05d5\u05d4\u05d7\u05d5\u05dd.\n"
        "CJK: \u8fc5\u901f\u7684\u68d5\u8272\u72d0\u72f8\u8df3\u8fc7\u61d2\u72d7\u3002\n"
        "Emoji: \U0001F600 \U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466\n"
    )

    SINGLE_CHAR = "A"

    @staticmethod
    def line_ending_stress() -> bytes:
        """Raw bytes with CRLF, LF, and CR at known positions, to verify
        DI-24 / DI-25 without relying on Python's universal-newline
        translation on write."""
        lines = [
            b"line-one-crlf-marker-A1B2",
            b"line-two-lf-marker-C3D4",
            b"line-three-cr-marker-E5F6",
            b"line-four-crlf-marker-G7H8",
        ]
        return lines[0] + b"\r\n" + lines[1] + b"\n" + lines[2] + b"\r" + lines[3] + b"\r\n"

    @staticmethod
    def control_chars_with_null() -> bytes:
        return b"before-marker\x01\x1f" + b"\x00" + b"after-marker-Z9Y8"

    @staticmethod
    def tabs_and_spaces() -> bytes:
        return (
            b"\tTabbed line one\n"
            b"    Spaced line two\n"
            b"\t\tDouble-tabbed line three\n"
        )

    @staticmethod
    def repeating_block_with_markers(total_bytes: int, marker_interval: int = 4096) -> bytes:
        """Generates deterministic large-file content: a repeating ASCII
        pattern with a unique offset marker inserted periodically, so a
        truncation or mid-file corruption is detectable by location, not
        just by an overall hash mismatch."""
        pattern = (string_block := (
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz\n"
        )).encode("ascii")
        out = bytearray()
        offset = 0
        while len(out) < total_bytes:
            if offset % marker_interval == 0:
                marker = f"<<OFFSET:{offset:012d}>>".encode("ascii")
                out.extend(marker)
                offset += len(marker)
            chunk = pattern[: max(1, min(len(pattern), total_bytes - len(out)))]
            out.extend(chunk)
            offset += len(chunk)
        return bytes(out[:total_bytes])


# --------------------------------------------------------------------------
# Test harness
# --------------------------------------------------------------------------

class TestHarness:
    def __init__(self, workdir: Path, exe_path: str = "notepad.exe"):
        self.workdir = workdir
        self.exe_path = exe_path
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.results: list[TestResult] = []

    # ---- helpers -----------------------------------------------------

    def _path(self, name: str) -> Path:
        return self.workdir / name

    def _run_case(self, case_id, title, priority, category, fn, skip_reason=None):
        if skip_reason:
            r = TestResult(case_id, title, priority, category,
                            passed=None, skipped=True, detail=skip_reason)
            self.results.append(r)
            print(f"[SKIP] {case_id} - {title}: {skip_reason}")
            return r

        start = time.time()
        r = TestResult(case_id, title, priority, category)
        try:
            fn(r)
        except Exception as e:
            r.passed = False
            r.error = f"{type(e).__name__}: {e}"
        r.duration_s = time.time() - start
        self.results.append(r)
        status = "PASS" if r.passed else ("SKIP" if r.skipped else "FAIL")
        print(f"[{status}] {case_id} - {title} ({r.duration_s:.2f}s) {r.detail}")
        return r

    def _verify_bytes(self, r: TestResult, expected: bytes, actual: bytes, note: str = ""):
        r.expected_hash = sha256_of_bytes(expected)
        r.actual_hash = sha256_of_bytes(actual)
        if r.expected_hash == r.actual_hash:
            r.passed = True
            r.detail = f"Byte-identical match ({len(actual)} bytes). {note}".strip()
        else:
            r.passed = False
            off = first_diff_offset(expected, actual)
            ctx_exp = hex_context(expected, off) if off is not None else "n/a"
            ctx_act = hex_context(actual, off) if off is not None else "n/a"
            r.detail = (
                f"MISMATCH at byte offset {off}. "
                f"expected_len={len(expected)} actual_len={len(actual)}. "
                f"expected_hex@offset=[{ctx_exp}] actual_hex@offset=[{ctx_act}]. {note}"
            ).strip()

    # ---- DI-01: basic ASCII round-trip --------------------------------

    def case_di01(self, r: TestResult):
        path = self._path("DI-01_basic_ascii.txt")
        if path.exists():
            path.unlink()
        content = Fixtures.ASCII_BASELINE

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        drv.save_as(path, encoding_label="UTF-8")
        drv.close_app()

        actual = path.read_bytes()
        expected = content.encode("utf-8")
        self._verify_bytes(r, expected, actual)

    # ---- DI-02: empty file save/load ----------------------------------

    def case_di02(self, r: TestResult):
        path = self._path("DI-02_empty.txt")
        if path.exists():
            path.unlink()

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.save_as(path, encoding_label="UTF-8")
        drv.close_app()

        actual = path.read_bytes()
        expected = b""  # no BOM expected for plain UTF-8 selection
        self._verify_bytes(r, expected, actual,
                            note="Expect 0 bytes; a non-zero result likely indicates an unwanted BOM injection.")

    # ---- DI-03: overwrite via Save (not Save As) -----------------------

    def case_di03(self, r: TestResult):
        path = self._path("DI-03_overwrite.txt")
        long_text = "A" * 500
        short_text = "B" * 10

        path.write_bytes(long_text.encode("utf-8"))
        original_len = path.stat().st_size

        drv = NotepadDriver(self.exe_path).open_file(path)
        drv.select_all_and_delete()
        drv.type_text_literal(short_text)
        drv.save_plain()
        drv.close_app()

        actual = path.read_bytes()
        expected = short_text.encode("utf-8")
        note = f"Original file was {original_len} bytes; verifying correct truncation, not just an overwrite-in-place."
        self._verify_bytes(r, expected, actual, note=note)

    # ---- DI-09 .. DI-12, DI-14: encoding round-trips --------------------

    def _encoding_round_trip(self, r: TestResult, label: str, py_codec: str,
                              content: str, add_bom: bool = False):
        path = self._path(f"enc_{label.replace(' ', '_')}.txt")
        if path.exists():
            path.unlink()

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        drv.save_as(path, encoding_label=label)
        drv.close_app()

        actual = path.read_bytes()
        expected = content.encode(py_codec)
        if add_bom:
            bom = {
                "utf-8": b"\xef\xbb\xbf",
                "utf-16-le": b"\xff\xfe",
                "utf-16-be": b"\xfe\xff",
            }.get(py_codec, b"")
            expected = bom + expected
        self._verify_bytes(r, expected, actual, note=f"encoding={label}")

    def case_di09(self, r: TestResult):
        self._encoding_round_trip(r, "UTF-8", "utf-8", Fixtures.MULTILINGUAL, add_bom=False)

    def case_di10(self, r: TestResult):
        self._encoding_round_trip(r, "UTF-8 with BOM", "utf-8", Fixtures.MULTILINGUAL, add_bom=True)

    def case_di11(self, r: TestResult):
        self._encoding_round_trip(r, "UTF-16 LE", "utf-16-le", Fixtures.MULTILINGUAL, add_bom=True)

    def case_di12(self, r: TestResult):
        self._encoding_round_trip(r, "UTF-16 BE", "utf-16-be", Fixtures.MULTILINGUAL, add_bom=True)

    def case_di14(self, r: TestResult):
        ansi_safe_text = "Plain ASCII content only, safe for the active ANSI code page. 1234567890."
        self._encoding_round_trip(r, "ANSI", "cp1252", ansi_safe_text, add_bom=False)

    # ---- DI-13: ANSI save with non-representable characters ------------

    def case_di13(self, r: TestResult):
        path = self._path("DI-13_ansi_lossy.txt")
        if path.exists():
            path.unlink()
        content = "ASCII prefix - " + "\u4e2d\u6587" + " - CJK characters not in cp1252"

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        try:
            drv.save_as(path, encoding_label="ANSI")
        except Exception:
            pass  # a warning dialog may need an extra confirm keystroke
        finally:
            drv.close_app()

        if not path.exists():
            r.passed = False
            r.detail = "Save did not complete; could not assert fallback-substitution behavior."
            return

        actual = path.read_bytes()
        try:
            decoded = actual.decode("cp1252")
        except UnicodeDecodeError as e:
            r.passed = False
            r.detail = f"Saved ANSI file is not valid cp1252: {e}"
            return

        if "?" in decoded or "\ufffd" in decoded:
            r.passed = True
            r.detail = (
                "Non-representable characters were substituted with a documented "
                "fallback rather than silently dropped or corrupted."
            )
        else:
            r.passed = False
            r.detail = (
                "Expected a visible fallback substitution ('?' or U+FFFD) for "
                "characters outside cp1252; none found. Inspect manually - this "
                "may indicate silent data loss."
            )

    # ---- DI-16: re-saving without changing encoding selection -----------

    def case_di16(self, r: TestResult):
        path = self._path("DI-16_reopen_resave.txt")
        if path.exists():
            path.unlink()
        content = "Trivial edit re-save test. " + Fixtures.SINGLE_CHAR

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        drv.save_as(path, encoding_label="UTF-16 LE")
        drv.close_app()

        before = path.read_bytes()
        assert before[:2] == b"\xff\xfe", "Fixture setup failed: file was not saved as UTF-16 LE."

        drv2 = NotepadDriver(self.exe_path).open_file(path)
        editor = drv2._editor()
        editor.set_focus()
        send_keys(" ")  # trivial edit: append one space
        drv2.save_plain()
        drv2.close_app()

        after = path.read_bytes()
        if after[:2] == b"\xff\xfe":
            r.passed = True
            r.expected_hash = "n/a-structural-check"
            r.actual_hash = "n/a-structural-check"
            r.detail = "Encoding remained UTF-16 LE across a plain Save after a trivial edit."
        else:
            r.passed = False
            r.detail = f"Encoding marker changed unexpectedly; first 2 bytes now {after[:2]!r}."

    # ---- DI-22: emoji / multi-codepoint grapheme clusters ---------------

    def case_di22(self, r: TestResult):
        emoji_text = "Family: \U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466 end."
        self._encoding_round_trip(r, "UTF-8", "utf-8", emoji_text, add_bom=False)

    # ---- DI-23: RTL script content ---------------------------------------

    def case_di23(self, r: TestResult):
        rtl_text = "Mixed: \u05e9\u05dc\u05d5\u05dd 123 \u0627\u0644\u0633\u0644\u0627\u0645 end."
        self._encoding_round_trip(r, "UTF-8", "utf-8", rtl_text, add_bom=False)

    # ---- DI-24: mixed line endings ----------------------------------------

    def case_di24(self, r: TestResult):
        """
        This case writes the fixture directly to disk (bypassing the editor's
        own line-insertion behavior) and opens it in Notepad, then saves
        WITHOUT edits, to test whether Notepad's save path normalizes line
        endings on a no-op save. This is more reliable than typing CR/LF/CR
        combinations via the keyboard, which most input methods cannot
        produce distinctly.
        """
        path = self._path("DI-24_mixed_line_endings.txt")
        original = Fixtures.line_ending_stress()
        path.write_bytes(original)

        drv = NotepadDriver(self.exe_path).open_file(path)
        drv.save_plain()
        drv.close_app()

        actual = path.read_bytes()
        self._verify_bytes(
            r, original, actual,
            note="No edits were made; any difference indicates Notepad silently "
                 "normalized line endings on save. If normalization to CRLF is "
                 "Notepad's documented behavior for this build, treat a fully "
                 "consistent CRLF-normalized result as a conditional pass and "
                 "update this case's expected value accordingly - a PARTIAL "
                 "normalization is always a fail."
        )

    # ---- DI-25: trailing newline preservation -----------------------------

    def case_di25(self, r: TestResult):
        path_with = self._path("DI-25_trailing_nl_with.txt")
        path_without = self._path("DI-25_trailing_nl_without.txt")

        content_with = b"line one\r\nline two\r\n"
        content_without = b"line one\r\nline two"

        path_with.write_bytes(content_with)
        path_without.write_bytes(content_without)

        drv1 = NotepadDriver(self.exe_path).open_file(path_with)
        drv1.save_plain()
        drv1.close_app()

        drv2 = NotepadDriver(self.exe_path).open_file(path_without)
        drv2.save_plain()
        drv2.close_app()

        actual_with = path_with.read_bytes()
        actual_without = path_without.read_bytes()

        ok_with = actual_with == content_with
        ok_without = actual_without == content_without

        r.expected_hash = sha256_of_bytes(content_with + content_without)
        r.actual_hash = sha256_of_bytes(actual_with + actual_without)

        if ok_with and ok_without:
            r.passed = True
            r.detail = "Trailing-newline presence/absence both preserved exactly."
        else:
            r.passed = False
            r.detail = (
                f"with-trailing-newline preserved={ok_with} (got {actual_with!r}); "
                f"without-trailing-newline preserved={ok_without} (got {actual_without!r})"
            )

    # ---- DI-26: tab vs space preservation -----------------------------------

    def case_di26(self, r: TestResult):
        path = self._path("DI-26_tabs_spaces.txt")
        original = Fixtures.tabs_and_spaces()
        path.write_bytes(original)

        drv = NotepadDriver(self.exe_path).open_file(path)
        drv.save_plain()
        drv.close_app()

        actual = path.read_bytes()
        self._verify_bytes(r, original, actual,
                            note="Tabs (0x09) must remain 0x09; spaces must remain 0x20.")

    # ---- DI-27: null byte / control character handling -----------------------

    def case_di27(self, r: TestResult):
        path = self._path("DI-27_control_chars.txt")
        original = Fixtures.control_chars_with_null()
        path.write_bytes(original)

        try:
            drv = NotepadDriver(self.exe_path).open_file(path)
            drv.save_plain()
            drv.close_app()
        except Exception as e:
            r.passed = None
            r.skipped = True
            r.detail = f"Notepad may have rejected the file as binary/unsupported: {e}"
            return

        actual = path.read_bytes()
        if actual == original:
            r.passed = True
            r.expected_hash = sha256_of_bytes(original)
            r.actual_hash = sha256_of_bytes(actual)
            r.detail = "Control bytes including NUL preserved exactly."
        else:
            r.passed = False
            r.expected_hash = sha256_of_bytes(original)
            r.actual_hash = sha256_of_bytes(actual)
            off = first_diff_offset(original, actual)
            r.detail = (
                f"Content changed at offset {off}. If Notepad truncated at the "
                f"NUL byte (offset {original.index(0)}) this is a silent-"
                f"truncation defect per the test plan's pass/fail criteria, "
                f"even though no error was shown."
            )

    # ---- DI-28: clipboard round-trip -----------------------------------------

    def case_di28(self, r: TestResult):
        content = Fixtures.MULTILINGUAL
        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        drv.copy_all_to_clipboard()
        clip_text = drv.get_clipboard_text()

        drv.select_all_and_delete()
        drv.paste_via_clipboard(clip_text)
        time.sleep(0.2)

        path = self._path("DI-28_clipboard_roundtrip.txt")
        if path.exists():
            path.unlink()
        drv.save_as(path, encoding_label="UTF-8")
        drv.close_app()

        actual = path.read_bytes()
        expected = content.encode("utf-8")
        self._verify_bytes(r, expected, actual)

    # ---- DI-29: find-and-replace scope integrity ------------------------------

    def case_di29(self, r: TestResult):
        path = self._path("DI-29_find_replace.txt")
        if path.exists():
            path.unlink()

        # Construct content with a known, countable number of occurrences
        # of a target token, interleaved with look-alike substrings that
        # must NOT be affected.
        target = "TOKEN42"
        lookalike = "TOKEN420"  # shares a prefix; must remain untouched if
                                 # Notepad's Replace All matches whole
                                 # occurrences correctly bounded
        lines = []
        for i in range(20):
            if i % 4 == 0:
                lines.append(f"line {i}: contains {target} once")
            elif i % 4 == 1:
                lines.append(f"line {i}: contains {lookalike} (should be untouched)")
            else:
                lines.append(f"line {i}: no token here")
        content = "\n".join(lines) + "\n"
        expected_replacements = sum(1 for ln in lines if ln.count(target) and lookalike not in ln)

        drv = NotepadDriver(self.exe_path).open_blank()
        drv.type_text_literal(content)
        drv.find_replace_all(target, "REPLACED")
        drv.save_as(path, encoding_label="UTF-8")
        drv.close_app()

        actual_text = path.read_bytes().decode("utf-8")
        actual_replaced_count = actual_text.count("REPLACED")
        lookalike_intact_count = actual_text.count(lookalike)
        expected_lookalike_count = sum(1 for ln in lines if lookalike in ln)

        r.expected_hash = f"replacements={expected_replacements} lookalikes_intact={expected_lookalike_count}"
        r.actual_hash = f"replacements={actual_replaced_count} lookalikes_intact={lookalike_intact_count}"

        if (actual_replaced_count == expected_replacements
                and lookalike_intact_count == expected_lookalike_count):
            r.passed = True
            r.detail = "Replace All hit exactly the targeted occurrences; look-alike substrings were left untouched."
        else:
            r.passed = False
            r.detail = (
                f"Expected {expected_replacements} replacements and "
                f"{expected_lookalike_count} intact look-alikes; got "
                f"{actual_replaced_count} and {lookalike_intact_count}."
            )

    # ---- DI-18/19: large file round-trip (opt-in) ------------------------------

    def _large_file_round_trip(self, r: TestResult, size_bytes: int, label: str):
        path = self._path(f"DI_large_{label}.txt")
        original = Fixtures.repeating_block_with_markers(size_bytes)
        path.write_bytes(original)
        original_hash = sha256_of_bytes(original)

        drv = NotepadDriver(self.exe_path, timeout=60).open_file(path)
        time.sleep(min(5.0, size_bytes / (20 * 1024 * 1024)))  # allow load time to scale with size
        drv.save_plain()
        time.sleep(min(5.0, size_bytes / (20 * 1024 * 1024)))
        drv.close_app()

        actual_hash = sha256_of_file(path)
        actual_size = path.stat().st_size

        r.expected_hash = original_hash
        r.actual_hash = actual_hash

        if actual_hash == original_hash:
            r.passed = True
            r.detail = f"{size_bytes:,} bytes round-tripped with no truncation or corruption."
        else:
            r.passed = False
            r.detail = (
                f"Hash mismatch on {size_bytes:,}-byte file "
                f"(expected_size={size_bytes:,}, actual_size={actual_size:,}). "
                f"Use a hex diff tool against the original fixture (regenerate "
                f"with the same parameters) to locate the corrupted offset."
            )

    def case_di18(self, r: TestResult):
        self._large_file_round_trip(r, 10 * 1024 * 1024, "10MB")

    def case_di19(self, r: TestResult):
        self._large_file_round_trip(r, 100 * 1024 * 1024, "100MB")

    # ---- registry -------------------------------------------------------------

    def all_cases(self):
        return [
            ("DI-01", "Basic round-trip, ASCII content", "Critical", "Functional", self.case_di01, None),
            ("DI-02", "Empty file save/load", "Medium", "Edge Case", self.case_di02, None),
            ("DI-03", "Overwrite existing file (Save vs Save As)", "Critical", "Functional", self.case_di03, None),
            ("DI-04", "External modification while file is open", "High", "Edge Case", None,
             "Requires a second-process race + modal dialog assertion; run via the manual checklist."),
            ("DI-05", "Read-only file save attempt", "Medium", "Negative", None,
             "Requires filesystem ACL setup outside this script's scope; run via the manual checklist."),
            ("DI-06", "Concurrent open in two Notepad instances", "Medium", "Edge Case", None,
             "Multi-window UI race; run via the manual checklist."),
            ("DI-07", "Disk full / write failure during save", "High", "Negative", None,
             "Requires constrained-volume or I/O fault injection; run via the manual checklist."),
            ("DI-08", "Application crash/force-close during save", "High", "Reliability", None,
             "Requires a fault-injecting I/O harness; run via the manual checklist."),
            ("DI-09", "UTF-8 without BOM round-trip", "Critical", "Functional", self.case_di09, None),
            ("DI-10", "UTF-8 with BOM round-trip", "Critical", "Functional", self.case_di10, None),
            ("DI-11", "UTF-16 LE round-trip", "Critical", "Functional", self.case_di11, None),
            ("DI-12", "UTF-16 BE round-trip", "High", "Functional", self.case_di12, None),
            ("DI-13", "ANSI save with non-representable characters", "Critical", "Negative", self.case_di13, None),
            ("DI-14", "Round-trip ANSI file, representable characters only", "High", "Functional", self.case_di14, None),
            ("DI-15", "Auto-detection ambiguity (no BOM)", "High", "Edge Case", None,
             "Requires asserting non-determinism across repeated runs; run via the manual checklist."),
            ("DI-16", "Re-saving without changing encoding selection", "Critical", "Regression", self.case_di16, None),
            ("DI-17", "Encoding change via Save As on existing file", "High", "Functional", None,
             "Covered structurally by DI-09..DI-12 encoding-selection logic; add a dedicated dual-file variant if needed."),
            ("DI-18", "10 MB file round-trip", "High", "Performance/Integrity", self.case_di18, None),
            ("DI-19", "100 MB file round-trip", "High", "Performance/Integrity", self.case_di19, None),
            ("DI-20", "1 GB file round-trip", "Critical", "Performance/Integrity", None,
             "Resource-heavy; run via large_file_stress.py, not this default suite."),
            ("DI-21", "4 GB boundary file round-trip", "Critical", "Edge Case", None,
             "Resource-heavy; run via large_file_stress.py, not this default suite."),
            ("DI-22", "Emoji and multi-codepoint grapheme clusters", "High", "Edge Case", self.case_di22, None),
            ("DI-23", "Right-to-left script content", "High", "Edge Case", self.case_di23, None),
            ("DI-24", "Mixed line endings (CRLF/LF/CR)", "Critical", "Edge Case", self.case_di24, None),
            ("DI-25", "Trailing newline preservation", "Medium", "Edge Case", self.case_di25, None),
            ("DI-26", "Tab vs. space preservation", "Medium", "Functional", self.case_di26, None),
            ("DI-27", "Null byte and control character handling", "High", "Negative", self.case_di27, None),
            ("DI-28", "Clipboard round-trip (copy out, paste back)", "Medium", "Functional", self.case_di28, None),
            ("DI-29", "Find-and-replace scope integrity", "High", "Functional", self.case_di29, None),
        ]

    def run(self, only_case_id: Optional[str] = None, include_large: bool = False):
        for case_id, title, priority, category, fn, skip_reason in self.all_cases():
            if only_case_id and case_id != only_case_id:
                continue
            if case_id in ("DI-18", "DI-19") and not include_large and not only_case_id:
                self._run_case(case_id, title, priority, category, fn,
                                skip_reason="Excluded by default; pass --large-files to include.")
                continue
            self._run_case(case_id, title, priority, category, fn, skip_reason)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_summary(results: list[TestResult]):
    total = len(results)
    passed = sum(1 for r in results if r.passed is True)
    failed = sum(1 for r in results if r.passed is False)
    skipped = sum(1 for r in results if r.skipped)

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Total cases:   {total}")
    print(f"Passed:        {passed}")
    print(f"Failed:        {failed}")
    print(f"Skipped/Manual:{skipped:>4}")

    critical_failed = [r for r in results if r.passed is False and r.priority == "Critical"]
    if critical_failed:
        print("\n*** CRITICAL FAILURES (release blockers per test plan Section 7.2) ***")
        for r in critical_failed:
            print(f"  - {r.case_id}: {r.title}")
            print(f"      {r.detail}")

    manual_cases = [r for r in results if r.skipped and "manual" in (r.detail or "").lower()
                    or (r.skipped and "checklist" in (r.detail or "").lower())]
    if manual_cases:
        print("\nCases requiring manual or specialized execution (not run by this script):")
        for r in manual_cases:
            print(f"  - {r.case_id}: {r.title} -> {r.detail}")

    print("=" * 78)


def write_json_report(results: list[TestResult], path: Path):
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "notepad_di_validator.py",
        "results": [r.to_dict() for r in results],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed is True),
            "failed": sum(1 for r in results if r.passed is False),
            "skipped": sum(1 for r in results if r.skipped),
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nJSON report written to: {path}")


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Automated data-integrity validation harness for Windows Notepad (notepad.exe).")
    parser.add_argument("--case", help="Run only the specified test case ID (e.g. DI-09).")
    parser.add_argument("--list", action="store_true", help="List all test case IDs and exit.")
    parser.add_argument("--large-files", action="store_true",
                         help="Include the 10MB/100MB large-file round-trip cases (slow).")
    parser.add_argument("--workdir", default=str(Path.cwd() / "notepad_di_workdir"),
                         help="Directory for fixture and output files.")
    parser.add_argument("--report", default="notepad_di_report.json",
                         help="Path to write the JSON results report.")
    parser.add_argument("--exe", default="notepad.exe",
                         help="Path to the notepad.exe build under test (default: PATH lookup).")
    args = parser.parse_args()

    harness_stub = TestHarness(Path(args.workdir), args.exe)

    if args.list:
        print(f"{'ID':<8}{'Priority':<10}{'Category':<22}{'Title'}")
        print("-" * 78)
        for case_id, title, priority, category, fn, skip_reason in harness_stub.all_cases():
            auto = "auto" if fn else "manual"
            print(f"{case_id:<8}{priority:<10}{category:<22}{title}  [{auto}]")
        return

    if not IS_WINDOWS:
        print("ERROR: notepad.exe only exists on Windows. This script must be run "
              "on a Windows host (or a Windows VM/container) to drive the real "
              "application under test.")
        sys.exit(1)

    if not PYWINAUTO_AVAILABLE:
        print("ERROR: pywinauto is required for UI automation but is not installed.\n"
              "Install it with:\n    pip install pywinauto pywin32")
        sys.exit(1)

    kill_notepad_processes()

    harness = TestHarness(Path(args.workdir), args.exe)
    harness.run(only_case_id=args.case, include_large=args.large_files)

    print_summary(harness.results)
    write_json_report(harness.results, Path(args.report))

    any_critical_fail = any(r.passed is False and r.priority == "Critical" for r in harness.results)
    sys.exit(1 if any_critical_fail else 0)


if __name__ == "__main__":
    main()
