# Contributing

Thank you for the interest. Three principles govern contributions here.

## Principles

1. **Verifiable only.** Every claim in docs or UI copy must map to code in the repo. If you add a feature claim, add the backing code **and** update `FACTS.md`.
2. **Trim before adding.** Prefer deleting 50 lines to adding 500. If a change adds abstraction, justify it in the PR body.
3. **The five pillars.** Resilient, Sovereign, Scalable, Affordable, Alternative. New code should strengthen at least one and weaken none.

## Workflow

```sh
git clone https://github.com/nzengou/africa-oracle-agent
cd africa-oracle-agent
python3 -m pip install -r requirements.txt pytest
python3 -m pytest tests/ -v      # baseline, must pass
# make your change on a feature branch
git checkout -b feat/my-change
# edit, test, repeat
python3 -m pytest tests/ -v
git commit -m "feat: short imperative subject"
git push -u origin feat/my-change
# open PR against main
```

## Required checks before PR

- [ ] `python3 -m pytest tests/ -v` → all green
- [ ] New or changed behavior has a test
- [ ] `README.md` and `FACTS.md` updated if public surface changed
- [ ] No hardcoded API keys / secrets
- [ ] No breaking change to the public API without a major-version bump
- [ ] Commit messages use the conventional-commits style (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)

## Quality gates (R²S²)

Every change must be **R**obust, **R**eliable, **S**olid, **S**table, **R**esistant, **S**calable, **S**ecure, **S**ystematic. See [`CLAUDE.md`](CLAUDE.md) for the full guardrail set.

Specific rules enforced by review:

- All external I/O must have timeout + error handling
- Financial math uses integers in smallest unit, no float
- Tests cover currency / country edge cases
- Any new dependency must be justified — the project stays pip-stdlib-adjacent on purpose

## Reporting a security issue

Not here. See [`SECURITY.md`](SECURITY.md).

## Attribution

Contributors are credited in `CHANGELOG.md` at each release. By submitting a PR, you agree to license your contribution under the same terms as the project.
