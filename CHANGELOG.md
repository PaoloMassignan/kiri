# Changelog

All notable changes to Kiri will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
