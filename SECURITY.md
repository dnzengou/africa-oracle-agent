# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.7.x   | ✅        |
| 0.6.x   | ✅ (security fixes only) |
| < 0.6   | ❌        |

Only the latest minor (`0.7.x`) receives feature changes; `0.6.x` receives security backports for 90 days from release.

## Reporting a vulnerability

Please **do not** open a public issue for security reports.

Preferred: open a private advisory via GitHub — **Security → Advisories → New draft** on this repository.

Alternative: email the maintainer with `[security]` in the subject line. Expect an acknowledgement within 72 hours and a triage decision within 7 days.

Include in your report:
- Affected version / commit hash
- Reproduction steps (minimal case preferred)
- Impact assessment (what can an attacker do, who is affected)
- Any suggested mitigation

## Scope

In scope:
- The oracle aggregator and robust / quorum filtering math (`oracle_agent.py`)
- The FastAPI server and all public endpoints (`api/app.py`)
- The embeddable widget (`/widget.js`)
- The SDKs (`sdk/`)
- The TON Jetton contract scaffold (`afri-token.fc`) — **note**: the contract is not deployed to mainnet; bugs in the scaffold are docs issues, not live exploits
- The Docker image and deployment configs

Out of scope:
- Vulnerabilities in third-party services (Fly.io, Vercel, GHCR, Telegram) — report to the respective vendor
- Issues requiring privileged local access to the user's machine
- Denial-of-service via volume — the project does not currently offer uptime SLAs
- Theoretical issues with no realistic attack vector

## Trust boundaries

- `--simulate` mode returns synthetic data; any claim of "live production rates" from that mode is a documentation bug, not a security bug.
- The public API does not store user funds; there is no custody surface to attack.
- Rate limit is per-process in-memory. In a horizontally scaled deployment, the limit is effectively `N × 60 req/min` across `N` workers. This is documented, not a bug.

## Responsible disclosure credit

Reporters who follow this policy will be credited in `CHANGELOG.md` and the GitHub advisory, unless they request anonymity.
