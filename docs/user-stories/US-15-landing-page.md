# US-15 — Public landing page

## Description

**As** a developer discovering Kiri,
**I want** to find a clear one-page explanation of what it does and how to try it,
**so that** I can evaluate it in 60 seconds and leave my email without reading any documentation.

---

## Expected behaviour

- A single static page publicly accessible at a stable URL (GitHub Pages or Vercel)
- No backend, no authentication, no database required
- Content: the problem (code leaking to LLMs without developers noticing), the two-line setup, the benchmark numbers, a form to request early access
- Links back to the GitHub repository

---

## Acceptance criteria

- [ ] Page is publicly accessible without login at a stable URL
- [ ] Shows a concrete 3-5 line example of how IP leaks today (e.g. `claude "refactor this class"` silently attaches the proprietary file)
- [ ] Shows the two-line setup: `export ANTHROPIC_BASE_URL=http://localhost:8765`
- [ ] Shows benchmark numbers prominently: F1=0.976 · Recall=1.0 · zero false negatives
- [ ] Contains a single "Request early access" CTA with email + company name (Tally or Typeform, no custom backend)
- [ ] Page loads in under 2 s on a mobile connection
- [ ] GitHub repository README links to the page
- [ ] Form submissions land in a spreadsheet accessible to the founder

---

## Notes

This is a go-to-market step, not a product feature. It belongs in Phase 2 because without it, traffic from Show HN or community posts has nowhere to land and interest is lost.

The source material already exists in `enterprise/archive/brief.md` — it reads almost like a landing page. Implementation is a static site (Astro, Hugo, or plain HTML/CSS) hosted on GitHub Pages or Vercel. Total build time: half a day.

Not in scope: demo widget, authentication, usage analytics beyond form submissions.
