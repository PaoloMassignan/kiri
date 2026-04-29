# Requirements — EARS Format

Requirements are written in **EARS** (Easy Approach to Requirements Syntax), a structured English notation that makes requirements unambiguous and testable.

## EARS templates

| Template | Syntax | Use |
|----------|--------|-----|
| Ubiquitous | `The [system] SHALL [capability]` | Always-active behavior |
| Event-driven | `WHEN [trigger] the [system] SHALL [capability]` | Response to an event |
| State-driven | `WHILE [state] the [system] SHALL [capability]` | Behavior in a specific state |
| Unwanted behavior | `IF [condition] THEN the [system] SHALL [capability]` | Error/exception handling |
| Complex | `WHILE [state] WHEN [trigger] the [system] SHALL [capability]` | Combined conditions |

## Files

| File | Contents |
|------|----------|
| [`functional.md`](functional.md) | Core functional requirements (interception, filtering, CLI) |
| [`security.md`](security.md) | Security requirements (auth, key management, audit) |
| [`non-functional.md`](non-functional.md) | Performance, availability, and operational requirements |

## Traceability

Each requirement has an ID (`REQ-F-NNN`, `REQ-S-NNN`, `REQ-NF-NNN`) that maps to:
- A user story in [`../user-stories/`](../user-stories/)
- One or more tests in [`../../kiri/tests/`](../../kiri/tests/)
