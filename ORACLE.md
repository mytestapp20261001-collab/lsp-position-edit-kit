# Fixture oracle

All strings, byte spans, LSP positions and final results in `fixtures.json` are literal, manually specified values. No release script regenerates them from `kit.py`. The tests additionally splice UTF-8 bytes using the literal spans and verify each sequential source snapshot and final text independently of the coordinate implementation.

## Hand-counted anchors

Positions are zero-based and ranges are half-open. ASCII characters use one unit in each tested encoding.

| Case | Prefix before target | UTF-8 bytes | UTF-16 units | UTF-32 units |
|---|---|---:|---:|---:|
| CJK | `变量 = ` | 9 | 5 | 5 |
| Astral | `😀 ` | 5 | 3 | 2 |
| Combining | `e` + U+0301 + space | 4 | 3 | 3 |
| ZWJ | U+1F469 + U+200D + U+1F4BB + space | 12 | 6 | 4 |

`target` is six ASCII units. The CJK target `name` is four. These counts produce the stored start/end columns without using the adapter.

For `😀\r\nname`, the second line starts at byte 6; `name` occupies bytes [6,10), LSP line 1 columns [0,4). Deleting bytes [4,6) removes the whole CRLF, represented by line 0 column 2 through line 1 column 0. In `a\r\n`, EOF is byte 3, line 1 column 0.

## Different change semantics

Sequential case, UTF-16:

1. `😀 x y\n`: insert `prefix ` at byte 0 / column 0
2. `prefix 😀 x y\n`: replace bytes [12,13), columns [10,11), with `renamed`
3. `prefix 😀 renamed y\n`: replace bytes [20,21), columns [18,19), with `end`
4. Expected result: `prefix 😀 renamed end\n`

Each event uses the previous event's result. Calculating every event's indices against the initial string fails this case.

Simultaneous case, UTF-16: the original string is `😀 aa bb\n`. Replace bytes [5,7), columns [3,5), with `longer`; also replace original bytes [8,10), columns [6,8), with `B`. Both positions refer to the original snapshot, so the result is `😀 longer B\n`. Applying the second range to the already expanded first result fails.

## Independence and limits

The literals, hand counts and byte-splice checks provide checks independent of the adapter under test. They are small reviewed engineering assertions, not a separately certified oracle, external adoption, or a full Unicode/LSP proof. Expected data is public, so this kit cannot detect an adapter that deliberately hard-codes the answers. Do not rewrite expected values to make a failing adapter pass; first inspect the specification, bytes and intended snapshot.
