# oli-eval — project brief

A small evaluation for Oli, Thommidhi's MCP connector that lets an AI assistant work with a creator's brand terms and deal desk. It checks which tools an assistant picks for realistic creator requests, what it gets wrong, and where the line sits between real data (the creator's words, the brand's message, Oli's results) and the model's own guesses.

## Files
- `oli_tools.json` — the 10 Oli tools, their write level (read / preview / write), inputs and allowed enum values. Source of truth for valid tool names and values.
- `transcripts/task1_2026-10-19_claude.json` — a REAL transcript (Claude + Oli, 19 Oct 2026). Tool names and arguments are exact. `assistant_reply` is a summary; `brand_facing_text` (turns 7 and 11) is the exact text drafted for the brand. Do not edit it.
- `requests.json` — the 20 creator requests with expected tool calls (written from the spec the user gives; don't invent requests).
- `score.py` — the scorer.
- `results/` — reports written by the scorer.
- `tests/` — fixture transcripts and unit tests for the scorer.

## Request format (requests.json)
Each request has: `id`, `group`, `request` (what the creator types), `context` (e.g. the brand's message, or null), `transcript_turns` (turns of the Task 1 transcript it maps to, or []), `why` (one line), and `expect` with any of:
- `must_call`: list of {tool, args?} that must appear (args must match)
- `must_not_call`: list of {tool, args?} patterns that must NOT appear
- `order`: tools that must appear in this order
- `no_duplicates`: tools that must not be called twice with identical args
- `must_ask_first`: true if no write or preview tool may be called in that turn
- `grounded_args`: {tool: [arg paths]} whose values must be traced to sources
- `changes_only`: allowed keys in propose_terms_update `changes`
- `no_empty_args`: true to flag any empty-string argument
- `args_present`: {tool: [arg paths]} that must be present
- `args_absent`: {tool: [arg paths]} that must NOT be present
- `notes_must_contain`: {tool: [strings]} for the `notes` argument
- `reply_must_not_contain`: strings that must not appear in brand-facing text
Every rule carries a `severity`: "fail" or "warn".

## Grounding levels
- DATA = the value appears in the creator's words, the brand's message, or an earlier Oli result in the same transcript. Numbers may be written as words or with commas ("Seven" = 7, "15,000" = 15000). 0 counts as DATA for "no <name>" / "without <name>" (e.g. "No exclusivity" → exclusivityDays 0).
- DERIVED = computed by a simple rule: months to days (×30), or "N days" counted from the transcript turn's date.
- GUESS = anything else.
Severity for every grounded arg: DATA = pass, DERIVED = warn, GUESS = fail.
Sources for a turn = all user text and request context up to and including that turn, plus all earlier tool results.

## Scoring (score.py)
Plain Python 3, standard library only, no network. Usage:
`python score.py requests.json transcripts/task1_2026-10-19_claude.json`
For each request with transcript_turns, collect that turn's tool calls and check every rule above. reply_must_not_contain checks `brand_facing_text` when present, else `assistant_reply`, using whole-word, case-insensitive matching; the report says which text was checked. A request's verdict is FAIL if any fail-severity rule breaks, else WARN if any warn rule breaks, else PASS. Also validate every call against oli_tools.json (tool exists, required args present, enum values valid).
Output: one line per request with reasons; requests not covered by the transcript listed as NOT RUN; a summary (verdict counts, tool choice correct, forbidden calls, duplicates, grounded values by DATA/DERIVED/GUESS, fee leaks and which texts were checked). Write the same report to `results/task1_report.md`. Always exit 0 unless the arguments are wrong.

## Rules
- Never call Thommidhi or Oli from this code. It only reads local files.
- Keep it small and readable; this is shipped evaluation code.
