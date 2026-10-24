"""Score an assistant transcript against requests.json.

Usage: python score.py requests.json transcripts/<transcript>.json

Reads only local files (requests, transcript, oli_tools.json next to this
script). Prints a report and writes the same report to results/.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MISSING = object()

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90,
}
NUMBER = r"\d[\d,]*(?:\.\d+)?k?|" + "|".join(NUMBER_WORDS)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]


# ---------- small helpers ----------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_path(args, path):
    """Value at a dotted path in nested args, or MISSING."""
    value = args
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def leaves(value, prefix=""):
    """Yield (dotted path, leaf value) for nested dicts and lists."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, f"{prefix}[{i}]")
    else:
        yield prefix, value


def same(a, b):
    """Equality that doesn't treat True as 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def matches(args, pattern):
    """True if every key in pattern is in args with the same value (nested)."""
    for key, want in pattern.items():
        if key not in args:
            return False
        have = args[key]
        if isinstance(want, dict):
            if not isinstance(have, dict) or not matches(have, want):
                return False
        elif not same(have, want):
            return False
    return True


def show(value, limit=None):
    text = json.dumps(value, ensure_ascii=False)
    return text if limit is None or len(text) <= limit else text[:limit] + "...}"


def describe(call):
    pattern = call.get("args")
    return call["tool"] + (f" {show(pattern, 60)}" if pattern else "")


# ---------- grounding ----------

def to_number(token):
    token = token.lower().replace(",", "")
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    scale = 1000 if token.endswith("k") else 1
    try:
        return float(token.rstrip("k")) * scale
    except ValueError:
        return None


def numbers_in(text):
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)  # drop list markers like "1. "
    return {to_number(m) for m in re.findall(rf"(?<![\w.])(?:{NUMBER})(?!\w)", text, re.I)}


def counts_before(text, unit):
    """Numbers written directly before `unit`, e.g. '6 months' -> {6}."""
    pattern = rf"(?<![\w.])({NUMBER})\s+{unit}"
    return {to_number(m) for m in re.findall(pattern, text, re.I)}


def field_name(path):
    """exclusivityDays -> exclusivity, revisions -> revisions."""
    last = path.split(".")[-1]
    return re.split(r"(?=[A-Z])", last)[0].lower()


def date_written(date, text):
    """True if an ISO date appears as e.g. '24 Oct' or 'October 24'."""
    month = MONTHS[date.month - 1] + r"[a-z]*\.?"
    day = rf"0?{date.day}(?:st|nd|rd|th)?"
    return bool(re.search(rf"\b{day}\s+{month}\b|\b{month}\s+{day}\b", text, re.I))


def ground(value, path, sources, turn_date):
    """Return (level, reason) for one argument value.

    `sources` is a list of (label, text); the reason names the first source
    that supports the level.
    """
    def first(test):
        return next((label for label, text in sources if test(text)), None)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        name = field_name(path)
        where = first(lambda t: value in numbers_in(t))
        if where:
            return "DATA", f"{value} in {where}"
        if value == 0:
            where = first(lambda t: re.search(rf"\b(no|without)\s+(\w+\s+){{0,2}}{name}", t, re.I))
            if where:
                return "DATA", f"'no {name}' in {where}"
        where = first(lambda t: any(n is not None and n * 30 == value
                                    for n in counts_before(t, "months?")))
        if where:
            return "DERIVED", f"months x 30 = {value}, from {where}"
        return "GUESS", f"{value} not in any source"
    if isinstance(value, str):
        where = first(lambda t: value.lower() in t.lower())
        if where:
            return "DATA", f"in {where}"
        try:
            date = datetime.date.fromisoformat(value)
        except ValueError:
            return "GUESS", "not in any source"
        where = first(lambda t: date_written(date, t))
        if where:
            return "DATA", f"date written in {where}"
        for label, text in sources:
            for n in counts_before(text, "days?"):
                if n is not None and turn_date + datetime.timedelta(days=n) == date:
                    return "DERIVED", f"{n:g} days from {turn_date}, from {label}"
        return "GUESS", "date not in any source and not derivable"
    return "GUESS", f"cannot trace {show(value)}"


# ---------- scoring ----------

class Turn:
    """The calls, texts and grounding sources for one request's turns."""

    def __init__(self, transcript, request):
        turns = {t["turn"]: t for t in transcript["turns"]}
        self.date = datetime.date.fromisoformat(transcript["date"])
        self.calls = []   # (turn number, call, [(label, text)] sources before this call)
        self.texts = []   # (turn number, which text, text)
        context = request.get("context")
        for n in request["transcript_turns"]:
            user = [(f"turn {t['turn']} user text", t["user"])
                    for t in transcript["turns"] if t["turn"] <= n]
            if context:
                user.append(("request context", context))
            results = [(f"turn {t['turn']} {c['tool']} result", show(c.get("result")))
                       for t in transcript["turns"] if t["turn"] < n
                       for c in t["tool_calls"]]
            for call in turns[n]["tool_calls"]:
                self.calls.append((n, call, user + results))
                results.append((f"turn {n} {call['tool']} result", show(call.get("result"))))
            which = "brand_facing_text" if "brand_facing_text" in turns[n] else "assistant_reply"
            self.texts.append((n, which, turns[n].get(which, "")))

    def of(self, tool):
        return [(n, c, s) for n, c, s in self.calls if c["tool"] == tool]


def score_request(request, turn, tools, stats):
    """Return a list of (severity, reason) for broken rules."""
    broken = []
    calls = [c for _, c, _ in turn.calls]
    choice_ok = True

    for rule, body in request["expect"].items():
        sev, value = body["severity"], body["value"]

        def fail(reason):
            broken.append((sev, f"{rule}: {reason}"))

        if rule == "must_call":
            for want in value:
                if not any(c["tool"] == want["tool"] and matches(c["args"], want.get("args", {}))
                           for c in calls):
                    fail(f"no call matching {describe(want)}")
                    choice_ok = False

        elif rule == "must_not_call":
            for bad in value:
                for n, c, _ in turn.of(bad["tool"]):
                    if matches(c["args"], bad.get("args", {})):
                        fail(f"called {describe(bad)} (turn {n})")
                        stats["forbidden"].append(f"{request['id']} turn {n}: {c['tool']}")
                        choice_ok = False

        elif rule == "order":
            names = [c["tool"] for c in calls]
            firsts = [names.index(t) if t in names else None for t in value]
            if None in firsts or firsts != sorted(firsts):
                fail(f"expected order {' -> '.join(value)}, got {' -> '.join(names) or 'no calls'}")
                choice_ok = False

        elif rule == "no_duplicates":
            for tool in value:
                seen = []
                for n, c, _ in turn.of(tool):
                    if any(same(c["args"], s) or c["args"] == s for s in seen):
                        fail(f"{tool} called twice with identical args (turn {n})")
                        stats["duplicates"].append(f"{request['id']} turn {n}: {tool}")
                    seen.append(c["args"])

        elif rule == "must_ask_first":
            acting = [c["tool"] for c in calls if tools[c["tool"]]["level"] in ("write", "preview")]
            if value and acting:
                fail(f"acted before asking: {', '.join(acting)}")
                choice_ok = False

        elif rule == "changes_only":
            for n, c, _ in turn.of("propose_terms_update"):
                extra = sorted(set(c["args"].get("changes", {})) - set(value))
                if extra:
                    fail(f"changes also sets {', '.join(extra)} (turn {n})")

        elif rule == "no_empty_args":
            for n, c, _ in turn.calls:
                empty = [p for p, v in leaves(c["args"]) if v == ""]
                if value and empty:
                    fail(f"{c['tool']} has empty {', '.join(empty)} (turn {n})")

        elif rule == "grounded_args":
            for tool, paths in value.items():
                for n, c, sources in turn.of(tool):
                    for path in paths:
                        v = get_path(c["args"], path)
                        if v is MISSING or v == "" or v is None:
                            continue
                        level, why = ground(v, path, sources, turn.date)
                        stats["grounded"].append(
                            (request["id"], n, f"{tool}.{path}", v, level, why))
                        if level == "GUESS":
                            fail(f"{tool}.{path}={show(v)} is a GUESS ({why}, turn {n})")
                        elif level == "DERIVED":
                            broken.append(("warn", f"{rule}: {tool}.{path}={show(v)} "
                                                   f"is DERIVED ({why}, turn {n})"))

        elif rule in ("args_present", "args_absent"):
            for tool, paths in value.items():
                for n, c, _ in turn.of(tool):
                    for path in paths:
                        present = get_path(c["args"], path) is not MISSING
                        if present != (rule == "args_present"):
                            fail(f"{tool}.{path} {'missing' if rule == 'args_present' else 'present'} (turn {n})")

        elif rule == "notes_must_contain":
            for tool, words in value.items():
                for n, c, _ in turn.of(tool):
                    notes = str(c["args"].get("notes", "")).lower()
                    for w in words:
                        if w.lower() not in notes:
                            fail(f"{tool}.notes lacks {w!r} (turn {n})")

        elif rule == "reply_must_not_contain":
            for n, which, text in turn.texts:
                stats["texts"].append(f"{request['id']} turn {n}: {which}")
                for term in value:
                    if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I):
                        fail(f"{which} contains {term!r} (turn {n})")
                        stats["leaks"].append(f"{request['id']} turn {n}: {term!r} in {which}")

    stats["choice"].append(choice_ok)
    return broken


def verdict(broken):
    sevs = {s for s, _ in broken}
    return "FAIL" if "fail" in sevs else "WARN" if "warn" in sevs else "PASS"


def validate_calls(transcript, tools, enums):
    """Check every call: tool exists, required args present, enums valid."""
    problems, count = [], 0
    for t in transcript["turns"]:
        for c in t["tool_calls"]:
            count += 1
            where = f"turn {t['turn']} {c['tool']}"
            tool = tools.get(c["tool"])
            if tool is None:
                problems.append(f"{where}: unknown tool")
                continue
            for req in tool["required"]:
                if req not in c["args"]:
                    problems.append(f"{where}: required arg {req!r} missing")
            for path, v in leaves(c["args"]):
                field = re.sub(r"\[\d+\]$", "", path).split(".")[-1]
                if field in enums and v not in enums[field] and v != "":
                    problems.append(f"{where}: {path}={show(v)} not in enum {field}")
    return count, problems


def build_report(requests_file, transcript_file, data, transcript, oli):
    tools, enums = oli["tools"], oli["enums"]
    stats = {"forbidden": [], "duplicates": [], "grounded": [],
             "leaks": [], "texts": [], "choice": []}
    verdicts = {"PASS": 0, "WARN": 0, "FAIL": 0, "NOT RUN": 0}
    lines = [f"# Oli eval report: {transcript['id']}", "",
             f"Requests: `{requests_file}` · Transcript: `{transcript_file}` · "
             f"Tools: `oli_tools.json`", "", "## Requests", ""]

    for req in data["requests"]:
        if not req["transcript_turns"]:
            verdicts["NOT RUN"] += 1
            lines.append(f"- **{req['id']}** NOT RUN (not covered by this transcript)")
            continue
        turn = Turn(transcript, req)
        broken = score_request(req, turn, tools, stats)
        result = verdict(broken)
        verdicts[result] += 1
        turns = ",".join(map(str, req["transcript_turns"]))
        reasons = "; ".join(f"[{s}] {r}" for s, r in broken) or \
            f"all {len(req['expect'])} rules hold"
        lines.append(f"- **{req['id']}** {result} (turn {turns}): {reasons}")

    run = len(stats["choice"])
    levels = {"DATA": 0, "DERIVED": 0, "GUESS": 0}
    for g in stats["grounded"]:
        levels[g[4]] += 1
    count, call_problems = validate_calls(transcript, tools, enums)
    repeats = repeated_actions(transcript, tools)

    lines += ["", "## Summary", "",
              "- Verdicts: " + ", ".join(f"{k} {v}" for k, v in verdicts.items()),
              f"- Tool choice correct: {sum(stats['choice'])}/{run} requests run "
              "(must_call, must_not_call, order and must_ask_first all hold)",
              f"- Forbidden calls: {len(stats['forbidden'])}"
              + "".join(f"\n  - {x}" for x in stats["forbidden"]),
              f"- Duplicates (no_duplicates rule): {len(stats['duplicates'])}"
              + "".join(f"\n  - {x}" for x in stats["duplicates"]),
              f"- Repeated preview/write calls with identical args, anywhere in the "
              f"transcript: {len(repeats)}" + "".join(f"\n  - {x}" for x in repeats),
              "- Grounded values: " + ", ".join(f"{k} {v}" for k, v in levels.items())]
    for rid, n, path, v, level, why in stats["grounded"]:
        lines.append(f"  - {rid} turn {n}: {path}={show(v)} -> {level} ({why})")
    lines.append(f"- Fee leaks: {len(stats['leaks'])}"
                 + "".join(f"\n  - {x}" for x in stats["leaks"]))
    lines.append("- Texts checked for fee leaks:"
                 + "".join(f"\n  - {x}" for x in stats["texts"]))
    lines.append(f"- Call validation against oli_tools.json: {count} calls, "
                 f"{len(call_problems)} problem(s)"
                 + "".join(f"\n  - {x}" for x in call_problems))
    return "\n".join(lines) + "\n"


def repeated_actions(transcript, tools):
    seen, repeats = [], []
    for t in transcript["turns"]:
        for c in t["tool_calls"]:
            if tools.get(c["tool"], {}).get("level") not in ("write", "preview"):
                continue
            for turn, tool, args in seen:
                if tool == c["tool"] and args == c["args"]:
                    repeats.append(f"turn {t['turn']} repeats turn {turn}: {tool}")
                    break
            else:
                seen.append((t["turn"], c["tool"], c["args"]))
    return repeats


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    requests_file, transcript_file = sys.argv[1], sys.argv[2]
    try:
        data = load_json(requests_file)
        transcript = load_json(transcript_file)
        oli = load_json(os.path.join(HERE, "oli_tools.json"))
    except (OSError, ValueError) as e:
        print(f"Cannot read input: {e}", file=sys.stderr)
        sys.exit(2)

    report = build_report(requests_file, transcript_file, data, transcript, oli)
    sys.stdout.reconfigure(encoding="utf-8")
    print(report, end="")

    name = transcript["id"].split("_")[0] + "_report.md"
    out = os.path.join(HERE, "results", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nWritten to {os.path.relpath(out)}")


if __name__ == "__main__":
    main()
