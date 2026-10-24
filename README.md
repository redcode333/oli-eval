# oli-eval

Oli is Thommidhi's MCP connector. It lets an AI assistant read and update a creator's
brand-work terms, check brand offers, and manage deals on their deal desk.

This eval takes realistic creator requests and checks three things about how an
assistant handled them:

- **Tool choice:** did it call the right Oli tools, in the right order, and avoid the
  ones it shouldn't touch (for example, saving terms before the creator approved them)?
- **Arguments:** are the values valid for Oli, and does anything leak that shouldn't
  (the creator's minimum fee in a message to a brand)?
- **Data or guess:** where did each important value come from?
  - **DATA:** it appears in the creator's words, the brand's message, or an earlier Oli result.
  - **DERIVED:** computed by a simple rule (6 months → 180 days, "within 5 days" → a date).
  - **GUESS:** anything else, i.e. the model made it up.

  DATA passes, DERIVED warns, GUESS fails.

## Files

```
oli_tools.json        the 10 Oli tools, their write level, inputs and allowed values
requests.json         20 creator requests with the expected behaviour for each
transcripts/          real sessions to score (kept local, not published)
score.py              the scorer
check_requests.py     sanity check for requests.json against oli_tools.json
results/              reports written by the scorer
tests/                fixture transcripts and unit tests
```

Everything is plain Python 3 with the standard library. Nothing calls Thommidhi or
Oli; the code only reads local files.

## Running it

```
python score.py requests.json transcripts/task1_2026-10-19_claude.json
python -m unittest discover tests
python check_requests.py
```

The scorer prints the report and writes the same text to `results/task1_report.md`.
It exits 0 unless the arguments are wrong.

Real transcripts are not in this repo. Put them in `transcripts/` locally; without
them, the regression test is skipped and the other tests still run.

A request is FAIL if any fail-level rule breaks, WARN if only warn-level rules break,
and PASS otherwise. Requests with no matching turn in the transcript are NOT RUN.

## Results: Task 1 transcript

| Request | Verdict | Reason |
|---|---|---|
| R01 terms setup | WARN | Correct tools, every value DATA; sent an empty `availableFrom` |
| R02 "Yees confirm" | WARN | Proposed the same terms again instead of confirming (Oli returned no `change_id`) |
| R03 read terms | PASS | |
| R06 check offer | WARN | `liveBy` DERIVED from "within 5 days", `exclusivityDays` 180 DERIVED from "6 months"; no fee leak in the brand questions |
| R07 save deal | FAIL | Brand name "Test brand (fictional smartphone accessories)" is a GUESS; the creator never gave one |
| R08 revised offer | PASS | |
| R11 "okk agreed" | PASS | Asked what was meant; no tool call |
| R12 draft reply | WARN | Empty `clarified.liveBy`; no fee leak in the brand reply |
| R13 "agreed… update" | FAIL | Marked the deal Agreed when the brand had only asked a question |

The other 11 requests are not in this transcript.

| Summary | |
|---|---|
| Verdicts | 3 PASS, 4 WARN, 2 FAIL, 11 NOT RUN |
| Tool choice correct | 7 of 9 |
| Forbidden calls | 2 (R02 turn 4, R13 turn 12) |
| Repeated proposals | Turns 4 and 14 resend turn 2's proposal (turn 14 was an approved retest) |
| Grounded values | 9 DATA, 3 DERIVED, 1 GUESS |
| Fee leaks | 0, checked in the exact brand drafts from turns 7 and 11 |
| Call validity | 20 of 20 calls valid against `oli_tools.json` |

## Testing

There are 10 unit tests in `tests/test_score.py`. Two fixture transcripts cover
requests R03, R04, R05, R10, R13, R15 and R17:

- `good_fixture.json`: an assistant that gets each one right. Every rule holds.
- `bad_fixture.json`: the same requests, each breaking a specific rule. The tests
  check that exactly those rules break, at the expected severity.

Between them, every rule type is exercised:

| Rule | Broken in | Holds in |
|---|---|---|
| must_call | R02, real transcript | good fixture |
| must_not_call | R03, R05, R13 | good fixture |
| order | R17 | R17, R01 |
| no_duplicates | T01 | T01 |
| must_ask_first | R05 | R05, R11 |
| grounded_args | R17 (GUESS) | R17 |
| changes_only | R04 | R04 |
| no_empty_args | T01 | T01 |
| args_present | R17 | R17 |
| args_absent | R10 | R10 |
| notes_must_contain | R10 | R10 |
| reply_must_not_contain | R15 | R15, R06, R12 |

Other tests:

- **Call validation:** an invalid enum value (`category: "electronics"`), a bad list
  value, a missing required argument and an unknown tool are all flagged.
- **Regression:** the 9 verdicts above are locked, so a scorer change can't move them
  without a test failing.
- **The tests do catch bugs:** in a scratch copy, the scorer was broken six different
  ways (`changes_only`, GUESS detection, `must_ask_first`, `notes_must_contain`,
  `args_present` / `args_absent`, `no_empty_args`), and the tests failed every time.

## Limitations

- **One real transcript.** 9 of the 20 requests map to it; the other 11 are NOT RUN.
- **Shortened export.** Tool results were cut down to the parts that matter for scoring.
- **Reply text.** `assistant_reply` is a summary. Only `brand_facing_text` (turns 7 and
  11) is the exact draft, so fee-leak checks are only exact there.
- **Number matching is generous.** A number counts as DATA if it appears anywhere in
  the sources. Small numbers like 1 or 7 match easily, so a guessed small number can
  pass as DATA.
- **R02 is Oli's fault, not the model's.** Its WARN comes from Oli returning no
  `change_id`, which made confirming impossible.
- **T01 is not a real request.** It lives in the tests only, because nothing in
  `requests.json` uses `no_duplicates`.

## Next steps

- Score more transcripts, e.g. a ChatGPT session with Oli, to compare assistants on
  the same requests.
- Rerun after Oli's tool descriptions change and compare the reports, to see whether
  the wording actually changes behaviour.
