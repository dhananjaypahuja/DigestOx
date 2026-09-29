# 0011. Vendor staff messages are context, not evidence; Slack falls back to email domains

- **Status:** Accepted
- **Date:** 2026-09-28
- **Decided by:** Dhananjay Pahuja, at session 3's fixture review
- **Drafted by:** Claude, AI coworker, in SageOx-recorded session 3

## Context

Session 3 builds the Slack and GitHub readers. Writing the thin fixtures in Slack's real
export format raised two questions DESIGN.md hadn't answered.

1. **Staff replies.** A shared channel holds the vendor's replies as well as the customer's
   ("can you send a member ID?"), and so do GitHub issue threads. Stored as ordinary signals,
   they would inflate a theme's signal and thread counts. A staff message in a channel that
   names no customer would also count as unattributed evidence. But dropping them would lose
   thread context the model needs in session 4.
2. **Attribution by email domain.** DESIGN.md attributed Slack messages by channel only, and
   CSV tickets by email domain. The plan's session 3 evidence asks for attribution by email
   domain to work, but the CSV workbench arrives in session 9. The fixtures' `#bivo-community`
   channel names no customer, and its messages come from several customers.

<!-- SOURCE: sageox adr:docs/decisions/0010-bind-every-run-to-an-evidence-snapshot.md -->

## Decision

1. **Every signal records who wrote it:** `author_role` is `customer` or `vendor`
   (migration `0006`).
   - **Slack:** the author is vendor staff when their workspace is one of
     `vendor.slack_team_ids`, or their email domain is one of `vendor.email_domains`, both in
     `pulse.toml`.
   - **GitHub:** the author is staff when `authorAssociation` is `OWNER`, `MEMBER`, or
     `COLLABORATOR`.
2. **Vendor messages are stored but never counted.** `v_run_signals`, which every run-scoped
   fact reads, excludes them. Thread context can still read them from `signals`.
3. **A signal's author role is fixed at its first import**, like its customer (decision
   [0010](0010-bind-every-run-to-an-evidence-snapshot.md)), and a trigger enforces it.
4. **Slack attribution:** the channel names the customer first. In a channel that names no
   customer, a customer author's email domain may, matched against `account_domains`. The
   address comes from the export's `users.json` and is never stored. Otherwise the message
   stays unattributed.
5. **The customer list** is loaded with `pulse accounts load <file>` (JSON), not kept in
   `pulse.toml`. Loading never removes an account or a domain, because evidence points at
   them.

## Consequences

- An import without a `[vendor]` section warns that staff replies will count as customer
  evidence.
- Changing `[vendor]` or the accounts later doesn't re-attribute stored signals. The import
  reports how many records kept their first attribution.
- GitHub authors are still unattributed until a mapping names them (DESIGN.md section 6).
- The role is binary. A contractor or partner posting for the vendor needs a domain or
  workspace in `[vendor]` to be recognised.

## Related decisions

- **Aligns with 0010:** the author role joins the fields fixed at a signal's first import;
  the evidence snapshot rules are unchanged.
- **Aligns with 0006:** it lets session 3 show its planned evidence (attribution by email
  domain) without pulling the CSV workbench forward.
- **Aligns with 0002:** Bivo and its staff stay fictional; `bivo.example` and workspace
  `T0BIVO0001` exist only in the fixtures and `pulse.toml`.
- **0009** was surfaced by `ox decision enrich` but doesn't apply: it governs where review
  context is kept, not how evidence is counted.

## References

- DESIGN.md, sections 4 and 6
- `src/customer_pulse/migrations/0006_vendor_messages.sql`, `attribution.py`, `accounts.py`
- `tests/test_ingest.py`, `tests/test_privacy_gate.py`
