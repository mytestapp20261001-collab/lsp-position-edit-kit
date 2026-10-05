# LSP position/edit kit

Catch edits that work on ASCII and shift after emoji, CJK or an earlier change.
This small Python standard-library kit checks an application boundary: **UTF-8 byte spans → negotiated LSP ranges → exact edited document**. It also separates sequential `didChange` updates from simultaneous `TextEdit` batches.

No server, editor, credentials, package installation or runtime network access is needed. The CLI uses only the 13 original synthetic cases shipped here and never edits source files. Python 3.12 or 3.13 is the initial supported scope; Linux is the tested platform. It is an acceptance aid, not an LSP conformance suite or production text library.

## Run

From the repository directory:

```sh
python -B kit.py
python -B -m unittest -v
```

`kit.py` prints one JSON report to stdout. The correct adapter returns exit 0 and:

```json
{"counts":{"passed":13,"failed":0,"skipped":0},"status":"passed"}
```

The actual report also contains its schema version, Python version and each case's calculated ranges and final text. To see the mistakes the corpus detects:

```sh
python -B kit.py --adapter wrong-units
python -B kit.py --adapter stale-changes
python -B kit.py --adapter serial-batch
```

These intentionally return exit **1**. Their failed-case counts are 7, 1 and 1 respectively. They show three application mistakes, not defects in Python, an editor or a named upstream project. Argument errors return exit 2.

## Optional: try the creator's game

This kit is made by the creator of [MyTest](https://mytest.app). If you feel like a separate game, the [private bot workshop](https://mytest.app/bot-workshop) lets you choose an opening move and moves after a win, tie or loss, then inspect a run of up to 20 rock-paper-scissors hands. You can change the rules and rerun, skip the game, or close it whenever you like. Your scripted bot is not an independent AI. Visiting is optional and has no role in the checks above; no productivity benefit is claimed.

## Use your own trusted adapter

Use your application's existing document library rather than adopting this example implementation as production infrastructure. In a local test file, import `Adapter` and `audit` and supply three explicit trusted callables:

```python
from kit import Adapter, audit
from your_project.lsp_test_bridge import to_lsp_range, receive_changes, apply_edits

report = audit(Adapter(
    name="my-application",
    convert=to_lsp_range,
    sequential=receive_changes,
    simultaneous=apply_edits,
    supported_encodings=("utf-16",),
))
assert report["counts"]["failed"] == 0, report
assert report["counts"]["skipped"] == 3  # optional UTF-8/32 cases were not tested
```

`your_project.lsp_test_bridge` is a placeholder for your own application test code, not a dependency to install. The three call signatures are:

- `convert(text, [start_byte, end_byte], encoding) -> {start: {line, character}, end: {line, character}}`. Byte spans are half-open UTF-8 offsets into the supplied snapshot
- `sequential(initial_text, changes, encoding) -> final_text`. Changes contain `range` and `text`; each range refers to the document produced by the preceding change. A real `didChange` notification carries these as `contentChanges`
- `simultaneous(initial_text, edits, encoding) -> final_text`. Every range refers to the original document. The kit's normalized envelope uses `text`; a bridge to native `TextEdit` must map it to `newText`

Conversion inputs for successive events include separately written source snapshots. Expected ranges are not passed to the adapter. Its returned ranges feed the application stage; both coordinates and exact final text are checked. The separate byte-splice oracle test checks fixture snapshots without calling the implementation's coordinate functions. See [ORACLE.md](ORACLE.md).

The CLI does not dynamically import adapters, launch user-specified programs or accept real source files. Importing your own adapter explicitly in a test process executes trusted application code and is **not a sandbox**. Keep the corpus synthetic; no private project content is needed.

## Encoding and supported boundary policy

Read the actual initialization exchange. `encoding_for(client_encodings, server_encoding)` validates the selected supported encoding; it does not perform a network handshake. Omitted selection defaults to UTF-16. UTF-16 support is implicit even when omitted from the client's list. Optional UTF-8/32 must have been offered before selection. Unknown selected encodings are outside this kit's implementation.

A UTF-16-only adapter reports `passed_with_skips` with three skipped cases. Skips are not passes. Declaring no UTF-16 support is rejected rather than counted as successful optional coverage.

The examples accept Unicode scalar text and LF, CRLF or CR line endings. A combining mark or ZWJ remains a separate encoded unit; a visible glyph is not a coordinate unit. Character offsets beyond a line's content clamp to that line's end. The kit deliberately rejects negative/non-integer positions, out-of-range lines, byte spans inside a scalar or CRLF, positions splitting an encoded scalar, reversed resolved ranges (after clamping), overlapping batch edits and equal-start batch edits. Lone surrogates are outside scope. These restrictions are **example input policy**, not universal protocol invalidity: LSP allows some same-start batch edits, and other libraries may handle boundary cases differently.

This corpus does not test transport, parser correctness, rename completeness, capability discovery, document version races, notebook documents, arbitrary overlap handling, security or language-server interoperability. A passing report proves only the executed cases with the supplied adapter.

## Prior art and sources

- [LSP 3.17 positions](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/types/position.md), [initialization capabilities](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/general/initialize.md), [didChange](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didChange.md) and [text edits](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/types/textEdit.md) define the relevant behavior
- [Microsoft TextDocument](https://github.com/microsoft/vscode-languageserver-node/tree/main/textDocument), [lsp-test](https://github.com/haskell/lsp/tree/master/lsp-test) and [pytest-lsp](https://lsp-devtools.readthedocs.io/en/latest/pytest-lsp/) already provide richer implementation and testing facilities. This kit supplies a tiny portable application-boundary corpus, not replacements for them
- [Serena issue #2064](https://github.com/oraios/serena/issues/2064) is an example of a reported code-point/UTF-16 integration problem. These fixtures are original and do not reproduce or validate that project's current status

## Maintenance

Initial scope is the fixed corpus and Python 3.12/3.13 standard library. GitHub CI records the exact commit and runtime on standard public Linux runners; nothing is uploaded by the tests. No auto-update service or telemetry is included. A specific integration report or failing regression can justify a correction; this repository does not promise new features or exhaustive ongoing protocol coverage. Useful reports identify the fixture, negotiated encoding, runtime and synthetic expected/actual result. Do not post private code or credentials.

MIT licensed. [SKILL.md](SKILL.md) is a repository-local agent task recipe; it is not automatically installed into anyone's assistant.
