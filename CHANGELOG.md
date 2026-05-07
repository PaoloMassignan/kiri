# Changelog

All notable changes to Kiri will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-05-07

### Added
- Directory and glob pattern protection: `kiri add src/engine/`, `kiri add "src/**/*.py"` — stored as `@glob` rules with automatic 60 s rescan for new files (US-14)
- OAuth passthrough mode for Claude Code Pro/Max: set `oauth_passthrough: true` in `.kiri/config.yaml`; the gateway accepts OAuth session tokens, runs the full filter pipeline, and forwards with the original token unchanged (US-16, REQ-S-010)
- Linux installer (`install/linux/`) with systemd user service and loginctl linger support
- All installers (macOS, Linux, Windows) now prompt for auth mode: API key or Claude Pro/Max OAuth
- How-to guide for Claude Code Pro/Max: `docs/guides/claude-pro-max.md`
- 65 new unit tests; 593 passing total

### Changed
- `kiri status` now shows protected directories/globs with file count before individual file paths
- `kiri rm <dir>/` removes the `@glob` rule and purges associated vectors (no double-purge for individually-listed files)

---

## [0.1.0] — 2026-04-27

### Added
- Three-level filter pipeline: L1 (vector similarity), L2 (symbol matching), L3 (Ollama classifier)
- REDACT engine: replaces protected function bodies with stub comments before forwarding
- File watcher: automatic re-indexing when `.kiri/secrets` changes
- CLI: `kiri add/rm/status/inspect/log/explain/key`
- Multi-language AST parsing: Python, C#, TypeScript, Go, Java, Rust, C++, C
- Docker-ready setup with `docker-compose.yml` and Docker secrets for the upstream key
- Rate limiting per kiri key
- Audit log (JSONL, append-only) with rotation
- `kiri explain` command: plain-language breakdown of why a request was filtered
- OpenAI-compatible protocol support (`/v1/chat/completions`)
- Pre-commit hook to prevent accidental commit of kiri keys
- 528 unit and security tests
