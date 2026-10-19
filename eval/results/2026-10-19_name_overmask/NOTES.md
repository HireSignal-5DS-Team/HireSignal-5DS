# T11b: anonymiser took skill / project phrases as the candidate's name (rules only + real-GPU chain re-run)

- Scope: the 52 gold CVs (the counterfactual bases are the same files). Before the fix, 4 CVs had a detected "name",
  all of them skill / project phrases (`before.csv`, categories only); 5 `[NAME]` replacements in total.
- Cause: on a Djinni CV with one section heading, everything before it is the "header", and the header-name rule took
  a 2-3 capitalised-word segment of a bullet / list line as the name.
- Fix (`services/profile/detect.py`, `find_name`): in the header search, a bullet line is skipped, and on a list line
  (`,` `;` `/`) only the first segment may be a name. Designed on the one dev case (P45); no phrase list. An ESCO
  label / alt-label guard was checked and dropped: none of the 4 phrases is an ESCO label.
- After: 0/52 CVs with a detected name (`after/summary.json`, `scripts/eval_anonymiser.py`): synthetic set leaks
  0/65, other people readable 0/5, facts kept 65/67 (= T06 after).
- Counterfactual names: Matcher input identical to the base for 312/312 name-gender variants (832/832 all families);
  injected name parts readable 0/312; stored identity = the injected name 312/312.
- Chain re-run, production settings, the 4 affected pairs (`bias/`, `decisions_before_after.json`): no requirement
  decision and no outcome changed vs before the fix; agreement with gold unchanged (P06 4/8, P43 6/8, P45 4/6,
  P49 7/8).
