#!/usr/bin/env python3
"""
large_file_stress.py

Opt-in companion to notepad_di_validator.py for test cases DI-20 (1 GB
round-trip) and DI-21 (4 GB boundary round-trip), per the test plan's note
that these are resource-heavy and should run on a dedicated schedule rather
than as part of the default suite (Section 8, Risks and Mitigations).

This is kept as a separate script so the default validator run stays fast,
and so this one can be scheduled independently (e.g. nightly) with its own
disk-space and timeout budget.

USAGE
-----
  python large_file_stress.py --size-gb 1     # DI-20
  python large_file_stress.py --size-gb 4     # DI-21 (4 GB boundary)
  python large_file_stress.py --size-gb 4 --bytes-over 1024   # 4GB + 1KB,
                                                                 to probe the
                                                                 2^32 boundary
                                                                 from the
                                                                 other side

Requires the same notepad_di_validator.py module alongside it (imports
Fixtures, sha256_of_file, NotepadDriver, kill_notepad_processes).
"""

import argparse
import sys
import time
from pathlib import Path

from notepad_di_validator import (
    Fixtures, sha256_of_file, sha256_of_bytes, NotepadDriver,
    kill_notepad_processes, IS_WINDOWS, PYWINAUTO_AVAILABLE,
)


def generate_large_fixture(path: Path, total_bytes: int, marker_interval: int = 1 << 20):
    """Streams the fixture directly to disk in chunks, to avoid holding
    multi-gigabyte buffers in memory."""
    chunk_target = 8 * 1024 * 1024
    pattern = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz\n"
    written = 0
    with open(path, "wb") as f:
        buf = bytearray()
        while written < total_bytes:
            if written % marker_interval == 0:
                marker = f"<<OFFSET:{written:014d}>>".encode("ascii")
                buf.extend(marker)
                written += len(marker)
            remaining = total_bytes - written
            chunk = pattern[: max(1, min(len(pattern), remaining))]
            buf.extend(chunk)
            written += len(chunk)
            if len(buf) >= chunk_target:
                f.write(buf)
                buf.clear()
        if buf:
            f.write(buf)
    assert path.stat().st_size == total_bytes, (
        f"Fixture generation size mismatch: wrote {path.stat().st_size}, expected {total_bytes}"
    )


def run(size_bytes: int, workdir: Path, exe_path: str, label: str):
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / f"large_fixture_{label}.txt"

    print(f"Generating {size_bytes:,}-byte fixture at {path} ...")
    t0 = time.time()
    generate_large_fixture(path, size_bytes)
    print(f"  done in {time.time() - t0:.1f}s")

    print("Hashing original fixture ...")
    original_hash = sha256_of_file(path)
    print(f"  SHA-256: {original_hash}")

    print("Opening in Notepad ...")
    drv = NotepadDriver(exe_path, timeout=120).open_file(path)
    # Allow generous load time scaled to size; large files can take
    # noticeably longer than the per-MB estimate used in the main suite.
    time.sleep(max(5.0, size_bytes / (15 * 1024 * 1024)))

    print("Saving (Ctrl+S, no edits) ...")
    drv.save_plain()
    time.sleep(max(5.0, size_bytes / (15 * 1024 * 1024)))
    drv.close_app()

    print("Hashing post-roundtrip file ...")
    actual_hash = sha256_of_file(path)
    actual_size = path.stat().st_size
    print(f"  SHA-256: {actual_hash}")
    print(f"  size: {actual_size:,} bytes (expected {size_bytes:,})")

    if actual_hash == original_hash:
        print(f"\nPASS: {label} round-trip is byte-identical.")
        return 0
    else:
        print(f"\nFAIL: {label} round-trip hash mismatch.")
        print("Re-run with a hex diff tool against a freshly generated fixture "
              "of the same size to locate the corrupted byte offset; this "
              "script intentionally avoids holding two multi-GB buffers in "
              "memory simultaneously for an in-process diff.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="DI-20 / DI-21 large-file stress round-trip.")
    parser.add_argument("--size-gb", type=float, required=True,
                         help="Target file size in GiB (e.g. 1 for DI-20, 4 for DI-21).")
    parser.add_argument("--bytes-over", type=int, default=0,
                         help="Additional bytes added past the GiB boundary, to probe "
                              "the 2^32-byte boundary from above (DI-21 variant).")
    parser.add_argument("--workdir", default=str(Path.cwd() / "notepad_di_workdir"))
    parser.add_argument("--exe", default="notepad.exe")
    args = parser.parse_args()

    if not IS_WINDOWS:
        print("ERROR: this must run on Windows against the real notepad.exe.")
        sys.exit(1)
    if not PYWINAUTO_AVAILABLE:
        print("ERROR: pywinauto is required. pip install pywinauto pywin32")
        sys.exit(1)

    size_bytes = int(args.size_gb * (1024 ** 3)) + args.bytes_over
    label = f"{args.size_gb}GB" + (f"+{args.bytes_over}B" if args.bytes_over else "")

    kill_notepad_processes()
    sys.exit(run(size_bytes, Path(args.workdir), args.exe, label))


if __name__ == "__main__":
    main()
