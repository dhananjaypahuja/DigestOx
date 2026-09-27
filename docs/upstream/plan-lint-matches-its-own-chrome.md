# `ox plan lint --file` flags a credit that only exists in ox's own script

**ox:** 0.18.0 (`f52d5c94`) · **Found:** observed and from source

## Summary

`ox plan lint --file page.html` reports `branding.overclaim` ("render credits SageOx but the
plan carried no enrichment") for authored pages that contain no credit at all. The match comes
from ox's own injected chrome, not from the page.

## Evidence

- `runPlanLintFile` injects the chrome before linting (`cmd/ox/plan.go:702`,
  `plan.InjectChrome(...)`).
- `LintBranding` looks for a footer credit with `footerCreditRe`,
  `(?i)enriched by SageOx` (`internal/plan/lint.go:158`). It searches the whole HTML.
- The injected script contains that phrase as a literal inside a conditional:
  `if (data.footer_credit) parts.push('Team context enriched by SageOx…')`
  (`internal/plan/assets/chrome.js:117`).
- So every unenriched page matches, even though `BuildChromeData` correctly sets
  `FooterCredit` to false.

## Suggested fix

Match only rendered markup, for example by removing `<script>` bodies before applying
`footerCreditRe`. Or build the credit string in `chrome.js` so the literal phrase never
appears in the source.

## Related

Two pieces of guidance disagree about the OX marker. `ox agent prime`'s plan guidance says ox
chrome owns the OX markers and authors shouldn't hand-write them. But `ox plan lint --strict`
on a saved, enriched, authored page fails `branding.ox-marker` unless the page itself contains
an element with `aria-label="SageOx insight"`. One of the two should change.
