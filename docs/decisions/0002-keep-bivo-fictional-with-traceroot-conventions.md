# 0002. Keep Bivo fictional and borrow TraceRoot's open-source conventions

- **Status:** Accepted
- **Date:** 2026-09-27
- **Decided by:** Dhananjay Pahuja
- **Drafted by:** Claude, AI coworker, in SageOx-recorded sessions

## Context

The demo needs a vendor with customers, a codebase with code areas, and GitHub issues. The
kickoff chose Bivo, an invented B2B platform that gym chains and coaching studios use for
AI-generated training and nutrition plans.

Dhananjay proposed using TraceRoot instead (`traceroot-ai/traceroot`, an open-source YC S25
startup, Apache-2.0 outside its `ee/` directories). The concerns raised were:

- **Invented complaints about a real product.** The fixtures would be invented customer
  complaints about a real company's product, in a public repo. The fictional notice lives in
  the README and manifest, not inside each data file.
- **Misleading issue links.** Synthetic issue URLs under TraceRoot's repo would point at real,
  different issues. It had 494 open.

Dhananjay decided to keep the fictional company and "get useful aspects from them under the
fictional company bivo".

## Decision

Bivo stays fictional, with its four fictional customers. Its local vendor repo borrows
TraceRoot's engineering conventions, reviewed at commit `d786ae7`:

- a REST layer split into routers, schemas, and services, plus a separate worker
- issue forms (environment, steps to reproduce, expected and actual behaviour, logs, version)
  that shape the synthetic issue bodies
- a label taxonomy: type, `P0` to `P3` priority, and per-area labels
- a contributing guide and agent instructions
- a lint check on agent edits

Not taken:

- anything under `ee/`
- TraceRoot's name
- its real issues and contributors (issue text isn't covered by the repo's licence, and the
  data must be synthetic)
- its `bypassPermissions` agent setting

## Consequences

- Bivo's repo looks like a real startup's without attributing problems to a real company.
- If a file is ever adapted rather than imitated, the vendor repo's `NOTICE` records it.
- Fixture issue URLs use `github.com/bivo-fictional/bivo-platform`, an owner that doesn't exist.

## Alternatives considered

- **TraceRoot as the vendor:** rejected for the reasons above.
- **TraceRoot with its founders' permission:** not pursued.
- **An invented developer-tools vendor:** not chosen.

## References

- DESIGN.md, section 12
- `docs/sessions/00-setup-and-plan.md`
