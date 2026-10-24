"""Unit tests for score.py. Run from oli-eval: python -m unittest discover tests"""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import score  # noqa: E402

ALL_RULES = {
    "must_call", "must_not_call", "order", "no_duplicates", "must_ask_first",
    "grounded_args", "changes_only", "no_empty_args", "args_present",
    "args_absent", "notes_must_contain", "reply_must_not_contain",
}

# No request in requests.json uses no_duplicates, and none of the fixture
# requests uses no_empty_args, so this test-only request covers both.
T01 = {
    "id": "T01",
    "group": "test",
    "request": "Check this offer.",
    "context": "FICTIONAL TEST OFFER from Zentrix Gadgets: one integration for NoteNest, ₹16,000, live by 10 Nov 2026, organic use only, 1 revision.",
    "transcript_turns": [],
    "why": "Test-only: covers no_duplicates and no_empty_args.",
    "expect": {
        "must_call": {"severity": "fail", "value": [{"tool": "check_offer"}]},
        "no_duplicates": {"severity": "warn", "value": ["check_offer"]},
        "no_empty_args": {"severity": "warn", "value": True},
    },
}

# Rules each request must break in bad_fixture.json, with their severity.
BAD_EXPECT = {
    "R03": {("must_not_call", "fail")},
    "R04": {("changes_only", "fail")},
    # R05's must_not_call also forbids propose_terms_update, so both break.
    "R05": {("must_ask_first", "fail"), ("must_not_call", "fail")},
    "R10": {("args_absent", "fail"), ("notes_must_contain", "warn")},
    "R13": {("must_not_call", "fail")},
    "R15": {("reply_must_not_contain", "fail")},
    "R17": {("order", "fail"), ("grounded_args", "fail"), ("args_present", "fail")},
    "T01": {("no_duplicates", "warn"), ("no_empty_args", "warn")},
}

# Verdicts for the real Task 1 transcript, as agreed with the creator.
REAL_EXPECT = {
    "R01": "WARN", "R02": "WARN", "R03": "PASS", "R06": "WARN", "R07": "FAIL",
    "R08": "PASS", "R11": "PASS", "R12": "WARN", "R13": "FAIL",
}


def load(name):
    return score.load_json(os.path.join(ROOT, name))


TOOLS = load("oli_tools.json")
REQUESTS = {r["id"]: r for r in load("requests.json")["requests"]}
REQUESTS["T01"] = T01


def new_stats():
    return {"forbidden": [], "duplicates": [], "grounded": [],
            "leaks": [], "texts": [], "choice": []}


def run_fixture(name):
    """Score each request against its turn in a fixture: {id: [(severity, rule)]}."""
    fixture = load(os.path.join("tests", name))
    out = {}
    for rid, turns in fixture["request_turns"].items():
        request = copy.deepcopy(REQUESTS[rid])
        request["transcript_turns"] = turns
        broken = score.score_request(request, score.Turn(fixture, request),
                                     TOOLS["tools"], new_stats())
        out[rid] = [(reason.split(":")[0], sev) for sev, reason in broken]
    return fixture, out


class GoodFixture(unittest.TestCase):
    def test_every_request_passes(self):
        _, results = run_fixture("good_fixture.json")
        for rid, broken in results.items():
            with self.subTest(rid):
                self.assertEqual(broken, [])

    def test_calls_are_valid(self):
        fixture, _ = run_fixture("good_fixture.json")
        _, problems = score.validate_calls(fixture, TOOLS["tools"], TOOLS["enums"])
        self.assertEqual(problems, [])


class BadFixture(unittest.TestCase):
    def test_breaks_exactly_the_expected_rules(self):
        _, results = run_fixture("bad_fixture.json")
        self.assertEqual(set(results), set(BAD_EXPECT))
        for rid, expected in BAD_EXPECT.items():
            with self.subTest(rid):
                self.assertEqual(set(results[rid]), expected)

    def test_verdicts(self):
        _, results = run_fixture("bad_fixture.json")
        for rid, expected in BAD_EXPECT.items():
            want = "FAIL" if any(s == "fail" for _, s in expected) else "WARN"
            with self.subTest(rid):
                self.assertEqual(score.verdict([(s, r) for r, s in results[rid]]), want)

    def test_calls_are_valid(self):
        # Rule breaks only; enum errors are tested separately below.
        fixture, _ = run_fixture("bad_fixture.json")
        _, problems = score.validate_calls(fixture, TOOLS["tools"], TOOLS["enums"])
        self.assertEqual(problems, [])


class CallValidation(unittest.TestCase):
    def check(self, call):
        transcript = {"turns": [{"turn": 1, "tool_calls": [call]}]}
        return score.validate_calls(transcript, TOOLS["tools"], TOOLS["enums"])[1]

    def test_invalid_enum_flagged(self):
        problems = self.check({"tool": "check_offer",
                               "args": {"product": "Earbuds", "category": "electronics"}})
        self.assertEqual(len(problems), 1)
        self.assertIn("not in enum category", problems[0])

    def test_invalid_enum_in_list_flagged(self):
        problems = self.check({"tool": "check_offer",
                               "args": {"product": "Earbuds", "deliverables": ["dedicated", "podcast"]}})
        self.assertEqual(len(problems), 1)
        self.assertIn("not in enum deliverables", problems[0])

    def test_missing_required_and_unknown_tool_flagged(self):
        self.assertIn("required arg 'deal_id' missing",
                      self.check({"tool": "update_deal", "args": {"stage": "open"}})[0])
        self.assertIn("unknown tool", self.check({"tool": "delete_deal", "args": {}})[0])


class RealTranscript(unittest.TestCase):
    def test_task1_verdicts(self):
        transcript = load(os.path.join("transcripts", "task1_2026-10-19_claude.json"))
        for rid, want in REAL_EXPECT.items():
            request = REQUESTS[rid]
            broken = score.score_request(request, score.Turn(transcript, request),
                                         TOOLS["tools"], new_stats())
            with self.subTest(rid):
                self.assertEqual(score.verdict(broken), want)


class Coverage(unittest.TestCase):
    def test_every_rule_type_breaks_somewhere(self):
        broken = {rule for rules in BAD_EXPECT.values() for rule, _ in rules}
        # must_call is broken by R02 in the real transcript (RealTranscript).
        self.assertEqual(broken | {"must_call"}, ALL_RULES)


if __name__ == "__main__":
    unittest.main()
