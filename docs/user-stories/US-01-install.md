# US-01 — Install the gateway

## Description

**As** a developer,
**I want** to install the gateway once,
**so that** from that point on all my calls to Claude Code pass through it automatically, without me having to do anything.

---

## Expected behaviour

- The installer configures the gateway as a system service (Windows Service / launchd on Mac)
- The service starts automatically at login — no manual start required
- Configures `ANTHROPIC_BASE_URL=http://localhost:8765` at the system level, so that all tools (Claude Code, Cursor, Copilot) use it automatically
- Creates `.kiri/` in the home directory as the default global store

---

## Acceptance criteria

- [ ] After installation, Claude Code works normally — the developer notices no difference
- [ ] The service is active after a reboot without manual intervention
- [ ] `ANTHROPIC_BASE_URL` is set at the system level, requiring no per-project configuration
- [ ] If the gateway is unreachable, calls pass directly to the upstream (fail-open) — work is never blocked

---

## Notes

The developer does not know the gateway exists. They install it once, then it disappears into the background.
