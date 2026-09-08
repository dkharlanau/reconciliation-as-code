# Agent-Ready Web Profile adoption

Start with the repository's governing instructions and `.arwp/adoption.json`. This is a publisher-authored adoption contract, not a ranking certification.

Audience: Migration engineers and business reviewers proving transformation outcomes. Useful action: Run a synthetic reconciliation and inspect failed controls and evidence.

## Sources and publication

- Canonical publication: https://dkharlanau.github.io/reconciliation-as-code/
- Profile source: `docs/ai/site-profile.json`; public location: `ai/site-profile.json` under the canonical site base.
- Authoritative site source: `docs`.
- Published directory: `_site`.
- Build evidence: `scripts/build_docs_site.py; .github/workflows/product-pages.yml`.
- Product claims are bounded by `README.md`, `docs/agent-manifest.json`; CLI or source availability does not imply a hosted agent endpoint.

## Editorial experiment

Compare row counts with business-state reconciliation when IDs, tolerances or record cardinality change.

Reuse the existing intent owner before adding a page. Put the direct answer, concrete example, sources and strongest limitation in visible HTML. Keep comparison criteria symmetric; state where another approach is a better fit. Label synthetic fixtures and first-party interpretations.

The tactic IDs in the adoption contract resolve against [the ARWP corpus](https://github.com/dkharlanau/agent-ready-web-profile/blob/main/knowledge/discoverability-corpus.json). New tactics require evidence and a measurable product consequence.

## Validation and baseline

Validate the profile against [the ARWP v0.1 schema](https://github.com/dkharlanau/agent-ready-web-profile/blob/main/schema/site-profile.schema.json). For generated project sites, run `node scripts/stage-arwp.mjs <published-directory>` after building; the Pages workflow stages the same profile and discovery link into its artifact.

Check the exact emitted JSON and HTML before release. After an authorized release, verify the canonical live URL, HTTP status, profile link and response body. Record crawl eligibility, index status, search clicks/impressions, useful-action completion and independent AI citation separately. Missing observations remain unavailable; no score is a ranking promise.

This application is local only. Existing unrelated changes, product telemetry constraints and publication approvals remain in force.
