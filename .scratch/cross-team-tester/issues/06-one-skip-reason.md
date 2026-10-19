# 06: Skip files by name the way Team 16 does

**What to build:** Our system decides `skipped[]` from the file's name alone, with the same answers as Team 16 for any path (TT-Q13): a changed file is skipped as `UNSUPPORTED_FILE_TYPE` unless its extension, compared case-insensitively, is one of `.py`, `.ipynb`, `.js`, `.ts`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.go`, `.rs`, `.rb`, `.sh`, `.sql`, `.md`, `.rst`, `.txt`, `.yaml`, `.yml`, `.json`, `.toml`, `.cfg`, `.ini`, `.csv`, or its exact name is `LICENSE`, `Makefile`, `Dockerfile`, `README` or `CODEOWNERS`. That holds for every change type, deletions and type changes included. The content checks (binary, over 1 MB, not UTF-8) stop adding skips, and symlinks and submodules get no rule of their own, so `BINARY_FILE`, `FILE_TOO_LARGE` and `NOT_UTF8` are gone. The lists live in our own `path_rules.json`; the code is ours.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. `rules.is_skipped` decides by name from the two lists in `path_rules.json`; `fetch.py` no longer reads any file (the binary, size and UTF-8 checks and the symlink rule are gone, and `DRIFTER_MAX_FILE_BYTES` with them). Our tester passes T-05 against the in-process system. The internal test repo's expected answers changed for `oversize`, `non-utf8` and `mixed` only; the published repo needs no republish, since its files are unchanged. Decided on 2026-10-18 (TT-Q13, which replaces the content safety net of TT-Q7 row 7).

**Spec:** docs/plan/decisions.md, TT-Q12 and TT-Q13; Team 16's `doctracker/system/classify.py`, `analysis.py` and `mapping-v1.yaml` at `0db21ca`; the student-facing spec ("behavior must match the shared specification. Teams choose their internal implementations.")

- [x] Every `skipped[]` entry is `UNSUPPORTED_FILE_TYPE`, and a file is skipped exactly when its name is outside the two lists.
- [x] `data/weights.bin` and `assets/logo.png` are skipped, `notes.TXT` and `Makefile` aren't, and a deleted `.png` is still skipped.
- [x] Our tester passes T-05 against the in-process system on the local fixture copy.
- [x] `tests/reference.py` loses `OUR_EXTRA_SKIP_REASONS`, and `docs/spec.md`, the README and `CONTEXT.md` describe the new rule.
- [x] The internal test repo's expected answers (`tools/testrepo.py`) are updated; no republish is needed, as its files didn't change.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, revised (TT-Q13).** This ticket used to keep our content checks as a safety net and only rename their reasons. Kaan chose the same answers as Team 16 for any file, not just the fixture, and their system skips by name alone, so a binary `.txt` or an oversized `.md` is no longer skipped here either. v1.1 reads no file contents, so nothing unchecked is passed off as checked; v1.2's LLM will need its own answer for files it can't read.
