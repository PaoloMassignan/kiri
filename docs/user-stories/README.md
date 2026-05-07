# User Stories

Each file describes one user story: actor, goal, acceptance criteria, and notes.

## Index

| Story | Title | Status |
|-------|-------|--------|
| [US-01](US-01-install.md) | Install the gateway | Backlog |
| [US-02](US-02-protect.md) | Protect a file or symbol | Implemented |
| [US-03](US-03-unprotect.md) | Remove protection | Implemented |
| [US-04](US-04-status.md) | Show protection status | Implemented |
| [US-05](US-05-inspect.md) | Inspect a prompt | Implemented |
| [US-06](US-06-reindex.md) | Re-index after changes | Partial — watcher monitors secrets file only, not protected source files |
| [US-07](US-07-refactoring.md) | Protect across refactoring | Implemented |
| [US-08](US-08-new-dev.md) | Onboard a new developer | Implemented |
| [US-09](US-09-audit-log.md) | Audit log | Implemented |
| [US-10](US-10-initial-index.md) | Initial index on startup | Implemented |
| [US-11](US-11-openai-protocol.md) | OpenAI protocol (Cursor) | Implemented |
| [US-12](US-12-rate-limiting.md) | Per-key rate limiting | Implemented |
| [US-13](US-13-summary-management.md) | View and edit protection summaries | Implemented |
| [US-14](US-14-directory-protection.md) | Protect a directory or glob pattern | Done |
| [US-15](US-15-landing-page.md) | Public landing page | Done |
| [US-16](US-16-oauth-support.md) | Claude Code OAuth passthrough (Pro/Max) | Done |

## Format

Each story follows the standard format:

```
As a [actor], I want [goal], so that [benefit].

Acceptance criteria:
- [ ] ...

Notes: ...
```

See [`../requirements/`](../requirements/) for the EARS-formatted requirements derived from these stories.

## Archived versions

Earlier v1 stories (before the requirements were stabilized) are in [`../../archive/user-stories-v1/`](../../archive/user-stories-v1/).
