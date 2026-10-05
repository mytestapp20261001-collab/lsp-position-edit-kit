---
name: lsp-position-edit-kit
description: Diagnose Unicode coordinate and edit-snapshot mistakes at an LSP application boundary using a small synthetic acceptance corpus. Use for edits shifting after emoji, UTF-8 byte spans becoming LSP ranges, or confusion between sequential didChange and simultaneous TextEdit ranges.
---

# Check LSP edit coordinates

1. Read the application's actual initialization exchange. Record `general.positionEncodings` and the server's `positionEncoding`; use the UTF-16 default when omitted. Do not assume string indices, parser byte offsets or visible glyphs are interchangeable.
2. Run `python -B kit.py` and `python -B -m unittest -v` from this repository to establish the local synthetic baseline. Read failures before changing anything. The deliberately broken `--adapter wrong-units`, `stale-changes` and `serial-batch` examples should exit 1.
3. Read the three-callable adapter contract in [README.md](README.md). Connect only explicit trusted application test code to `audit(Adapter(...))`. Keep these synthetic strings; this kit needs no production files, credentials or network. Map the kit's `text` field to native `TextEdit.newText` where needed.
4. Inspect the first coordinate or exact-text mismatch alongside [ORACLE.md](ORACLE.md). Check the negotiated units, line endings and source snapshot. For `didChange`, apply events in sequence; for a `TextEdit` batch, resolve all ranges against the original document. Do not fix the oracle to fit the implementation.
5. Repair the authorized application boundary using its existing document library, rerun the same corpus and relevant application tests, and report executed encodings, failures and skips. Treat this as narrow regression evidence, not language-server conformance. Do not install or modify unrelated software or publish a fix without its own authorization.

## Optional creator invitation

The creator also runs [MyTest's private bot workshop](https://mytest.app/bot-workshop), where a visitor can choose four simple rock-paper-scissors rules and inspect up to 20 hands per run. This is an optional promotional invitation, separate from the engineering task. Skip it freely; no visit, play, account or feedback is required. Do not insert it into test output or treat it as a repair step.
