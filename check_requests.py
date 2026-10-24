"""Validate requests.json against oli_tools.json and print a summary table.

Usage: python check_requests.py [requests.json] [oli_tools.json]
Exits 1 if any problem is found.
"""
import json
import sys

RULES = {
    "must_call", "must_not_call", "order", "no_duplicates", "must_ask_first",
    "grounded_args", "changes_only", "no_empty_args", "args_present",
    "args_absent", "notes_must_contain", "reply_must_not_contain",
}
REQUEST_KEYS = {"id", "group", "request", "context", "transcript_turns", "why", "expect"}


def flatten(args, prefix=""):
    """Yield (dotted path, value) for every leaf in a nested args dict."""
    for key, value in args.items():
        path = prefix + key
        if isinstance(value, dict) and value:
            yield from flatten(value, path + ".")
        else:
            yield path, value


def path_ok(tool, path):
    """True if `path` names an input of `tool` (or a field inside one)."""
    inputs = tool["inputs"]
    return (path in inputs
            or path.split(".")[0] in inputs
            or any(i.startswith(path + ".") for i in inputs))


def check(requests_file, tools_file):
    with open(requests_file, encoding="utf-8") as f:
        data = json.load(f)
    with open(tools_file, encoding="utf-8") as f:
        oli = json.load(f)
    tools, enums = oli["tools"], oli["enums"]
    problems = []

    def check_tool(where, name):
        if name not in tools:
            problems.append(f"{where}: unknown tool {name!r}")
            return None
        return tools[name]

    def check_call(where, call):
        tool = check_tool(where, call.get("tool"))
        if tool is None:
            return
        for path, value in flatten(call.get("args", {})):
            if not path_ok(tool, path):
                problems.append(f"{where}: {call['tool']} has no input {path!r}")
            field = path.split(".")[-1]
            if field in enums:
                for v in value if isinstance(value, list) else [value]:
                    if v not in enums[field]:
                        problems.append(f"{where}: {path}={v!r} not in enum {field}")

    def check_paths(where, value):
        for name, paths in value.items():
            tool = check_tool(where, name)
            for path in paths if tool else []:
                if not path_ok(tool, path):
                    problems.append(f"{where}: {name} has no input {path!r}")

    ids = set()
    for req in data["requests"]:
        rid = req.get("id", "?")
        if rid in ids:
            problems.append(f"{rid}: duplicate id")
        ids.add(rid)
        missing = REQUEST_KEYS - req.keys()
        if missing:
            problems.append(f"{rid}: missing keys {sorted(missing)}")
        if req.get("group") not in data.get("groups", {}):
            problems.append(f"{rid}: unknown group {req.get('group')!r}")

        for rule, body in req.get("expect", {}).items():
            where = f"{rid}.{rule}"
            if rule not in RULES:
                problems.append(f"{where}: unknown rule")
                continue
            if not isinstance(body, dict) or body.get("severity") not in ("fail", "warn"):
                problems.append(f"{where}: severity must be 'fail' or 'warn'")
                continue
            value = body.get("value")
            if rule in ("must_call", "must_not_call"):
                for call in value:
                    check_call(where, call)
            elif rule in ("order", "no_duplicates"):
                for name in value:
                    check_tool(where, name)
            elif rule == "changes_only":
                for key in value:
                    if "changes." + key not in tools["propose_terms_update"]["inputs"]:
                        problems.append(f"{where}: unknown changes key {key!r}")
            elif rule in ("grounded_args", "args_present", "args_absent", "notes_must_contain"):
                if rule == "notes_must_contain":
                    value = {name: ["notes"] for name in value}
                check_paths(where, value)

    return data, problems


def count(req, rule):
    return len(req["expect"].get(rule, {}).get("value", []))


def main():
    if len(sys.argv) > 3:
        sys.exit(__doc__)
    requests_file = sys.argv[1] if len(sys.argv) > 1 else "requests.json"
    tools_file = sys.argv[2] if len(sys.argv) > 2 else "oli_tools.json"
    data, problems = check(requests_file, tools_file)

    print(f"{'id':<5}{'group':<7}{'turns':<8}{'must_call':>10}{'must_not_call':>15}")
    for req in data["requests"]:
        turns = ",".join(map(str, req["transcript_turns"])) or "-"
        print(f"{req['id']:<5}{req['group']:<7}{turns:<8}"
              f"{count(req, 'must_call'):>10}{count(req, 'must_not_call'):>15}")
    print(f"\n{len(data['requests'])} requests, {len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
