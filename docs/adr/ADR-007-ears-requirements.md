# ADR-007: Requirements in EARS format

## Status
Accepted

## Context

Requirements written in free prose (e.g. "the system must block suspicious requests")
present three problems for an AI-assisted project:

1. **Not verifiable:** it is not clear what constitutes "suspicious" or when the requirement is met
2. **Ambiguous:** "must" can mean a hard constraint or a desired behavior
3. **Not mappable:** an AI reading the code cannot link the code to a requirement

User stories in the "As X, I want Y, so that Z" format describe the _why_ but not
_exactly what_ the system must do in testable terms.

## Decision

Use **EARS** (Easy Approach to Requirements Syntax) for functional, security,
and non-functional requirements. User stories remain for context and motivation.

EARS uses structured English templates with explicit subject/verb/condition:

```
WHEN [trigger] the [system] SHALL [capability]
WHILE [state] the [system] SHALL [capability]
IF [condition] THEN the [system] SHALL [capability]
The [system] SHALL [capability]    ← ubiquitous (no trigger)
```

`SHALL` indicates a mandatory requirement. The subject is always the system.

**Traceability:**
- Each requirement has an ID (`REQ-F-NNN`, `REQ-S-NNN`, `REQ-NF-NNN`)
- Each requirement points to the tests that verify it
- Each requirement points to the user story that motivates it

## Consequences

**Positive:**
- Verifiable requirements: an AI can read `REQ-F-001` and find the corresponding test
- No ambiguity on triggers and conditions
- Gaps between requirements and tests are immediately visible
- Facilitates TDD: write the requirement → write the test → write the code

**Negative:**
- EARS requires more initial effort than free prose
- Some emergent requirements (found in code without an explicit requirement)
  require a back-filling pass

**Adopted conventions:**
- Language: English (for compatibility with tools, AI, international teams)
- Prefixes: `REQ-F-` (functional), `REQ-S-` (security), `REQ-NF-` (non-functional)
- Each requirement is atomic — describes a single behavior

## Alternatives considered

**IEEE 830 (structured prose):**
- Complete standard but verbose — fixed sections that produce long documents
- Difficult to keep up to date in a rapidly evolving project

**Gherkin (Given/When/Then):**
- Excellent for acceptance scenarios, less suited for system requirements
- Depends on a BDD framework (Cucumber, Behave) — additional overhead

**User stories as the sole requirements artifact:**
- Not precise enough for security and NFR requirements
- Difficult to trace "exactly what does the system do in this edge case"
