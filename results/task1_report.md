# Oli eval report: task1_2026-10-19_claude

Requests: `requests.json` · Transcript: `transcripts/task1_2026-10-19_claude.json` · Tools: `oli_tools.json`

## Requests

- **R01** WARN (turn 1,2): [warn] no_empty_args: propose_terms_update has empty changes.availableFrom (turn 2)
- **R02** WARN (turn 4): [warn] must_call: no call matching confirm_terms_update; [warn] must_not_call: called propose_terms_update {"creator_said": "\"Minimum fee: ₹15,000 per integration\" /...} (turn 4)
- **R03** PASS (turn 6): all 2 rules hold
- **R04** NOT RUN (not covered by this transcript)
- **R05** NOT RUN (not covered by this transcript)
- **R06** WARN (turn 7): [warn] grounded_args: check_offer.exclusivityDays=180 is DERIVED (months x 30 = 180, from turn 7 user text, turn 7); [warn] grounded_args: check_offer.liveBy="2026-10-24" is DERIVED (5 days from 2026-10-19, from turn 7 user text, turn 7)
- **R07** FAIL (turn 8): [fail] grounded_args: save_deal.brand="Test brand (fictional smartphone accessories)" is a GUESS (not in any source, turn 8); [warn] grounded_args: save_deal.liveBy="2026-10-24" is DERIVED (5 days from 2026-10-19, from turn 7 user text, turn 8)
- **R08** PASS (turn 9): all 2 rules hold
- **R09** NOT RUN (not covered by this transcript)
- **R10** NOT RUN (not covered by this transcript)
- **R11** PASS (turn 10): all 2 rules hold
- **R12** WARN (turn 11): [warn] no_empty_args: update_deal has empty clarified.liveBy (turn 11)
- **R13** FAIL (turn 12): [fail] must_not_call: called update_deal {"stage": "agreed"} (turn 12)
- **R14** NOT RUN (not covered by this transcript)
- **R15** NOT RUN (not covered by this transcript)
- **R16** NOT RUN (not covered by this transcript)
- **R17** NOT RUN (not covered by this transcript)
- **R18** NOT RUN (not covered by this transcript)
- **R19** NOT RUN (not covered by this transcript)
- **R20** NOT RUN (not covered by this transcript)

## Summary

- Verdicts: PASS 3, WARN 4, FAIL 2, NOT RUN 11
- Tool choice correct: 7/9 requests run (must_call, must_not_call, order and must_ask_first all hold)
- Forbidden calls: 2
  - R02 turn 4: propose_terms_update
  - R13 turn 12: update_deal
- Duplicates (no_duplicates rule): 0
- Repeated preview/write calls with identical args, anywhere in the transcript: 2
  - turn 4 repeats turn 2: propose_terms_update
  - turn 14 repeats turn 2: propose_terms_update
- Grounded values: DATA 9, DERIVED 3, GUESS 1
  - R01 turn 2: propose_terms_update.changes.rateFloor=15000 -> DATA (15000 in turn 1 user text)
  - R01 turn 2: propose_terms_update.changes.leadDays=7 -> DATA (7 in turn 2 user text)
  - R01 turn 2: propose_terms_update.changes.revisions=1 -> DATA (1 in turn 2 user text)
  - R01 turn 2: propose_terms_update.changes.exclusivityDays=0 -> DATA ('no exclusivity' in turn 1 user text)
  - R06 turn 7: check_offer.fee=12000 -> DATA (12000 in turn 7 user text)
  - R06 turn 7: check_offer.revisions=3 -> DATA (3 in turn 7 user text)
  - R06 turn 7: check_offer.exclusivityDays=180 -> DERIVED (months x 30 = 180, from turn 7 user text)
  - R06 turn 7: check_offer.liveBy="2026-10-24" -> DERIVED (5 days from 2026-10-19, from turn 7 user text)
  - R07 turn 8: save_deal.brand="Test brand (fictional smartphone accessories)" -> GUESS (not in any source)
  - R07 turn 8: save_deal.fee=12000 -> DATA (12000 in turn 7 user text)
  - R07 turn 8: save_deal.liveBy="2026-10-24" -> DERIVED (5 days from 2026-10-19, from turn 7 user text)
  - R12 turn 11: update_deal.clarified.fee=18000 -> DATA (18000 in turn 9 user text)
  - R12 turn 11: update_deal.clarified.revisions=1 -> DATA (1 in turn 2 user text)
- Fee leaks: 0
- Texts checked for fee leaks:
  - R06 turn 7: brand_facing_text
  - R12 turn 11: brand_facing_text
- Call validation against oli_tools.json: 20 calls, 0 problem(s)
