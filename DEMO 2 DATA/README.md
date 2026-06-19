# Notepad.exe Data Integrity Validator

Executable Python implementation of the automatable test cases from
*Test Plan: Data Integrity Validation — Notepad.exe* (DI-01 .. DI-29).

## Requirements

- Windows 10/11 with `notepad.exe` available
- Python 3.9+
- `pip install -r requirements.txt`

## Files

| File | Purpose |
|---|---|
| `notepad_di_validator.py` | Main harness: 22 automated test cases (DI-01–03, 09–14, 16, 18–19, 22–29) |
| `large_file_stress.py` | Opt-in companion for DI-20 (1 GB) and DI-21 (4 GB boundary) — run on a separate schedule |
| `requirements.txt` | `pywinauto` + `pywin32` |

## Usage

```
python notepad_di_validator.py --list                  # show all cases, auto vs manual
python notepad_di_validator.py                          # run the full automated suite
python notepad_di_validator.py --case DI-09             # run a single case
python notepad_di_validator.py --large-files            # also include DI-18/DI-19 (10MB/100MB)
python notepad_di_validator.py --workdir D:\di_test --report report.json

python large_file_stress.py --size-gb 1                 # DI-20
python large_file_stress.py --size-gb 4                 # DI-21
```

Exit code is non-zero if any **Critical**-priority case fails, matching the
test plan's Section 7.2 exit criteria (no unresolved Critical defect is
allowed to pass).

## How pass/fail is decided

Every case follows the plan's Section 4.4 rule: a SHA-256 hash (or full byte
diff) of the recovered content against the expected baseline is the sole
pass/fail signal. Visual inspection or the absence of an on-screen warning
is never sufficient — a case fails if the bytes differ, even silently.

## Cases requiring manual/specialized execution

Flagged by `--list` as `[manual]` and printed at the end of every run, not
silently skipped:

| ID | Reason |
|---|---|
| DI-04 | External modification race + modal dialog assertion |
| DI-05 | Filesystem ACL/read-only setup outside script scope |
| DI-06 | Multi-window UI race across two Notepad instances |
| DI-07 | Disk-full / I/O fault injection |
| DI-08 | Crash/force-close fault injection |
| DI-15 | Requires asserting non-determinism across repeated runs |
| DI-17 | Covered structurally by DI-09–12; add a dedicated dual-file variant if needed |
| DI-20 / DI-21 | Resource-heavy — use `large_file_stress.py` on a separate schedule |

## Adapting to your Notepad build

`NotepadDriver.save_as()` targets the modern Store-delivered Save As dialog
(filename `Edit` control + encoding `ComboBox`). If you're testing the
legacy inbox Notepad or a build with a different dialog layout, adjust the
control identifiers in that method — run with `pywinauto`'s
`print_control_identifiers()` on the live dialog to find the correct names
for your build.
