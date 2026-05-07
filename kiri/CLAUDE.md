# AI Gateway — Claude Code Instructions

This project runs **Kiri** on localhost:8765 that intercepts
all LLM calls and prevents proprietary source code from being sent to external
APIs. The gateway is transparent — it requires no changes to your normal Claude
Code workflow.

---

## Gateway Management

You can manage protection in natural language. Claude Code will translate your
request into the right `gateway` CLI command and run it.

### Protecting files and symbols

**"protect this file"** / **"add to secrets"**

Run: `kiri add <path>`

When the user refers to "this file" or "the current file", use the path of the
file currently open or most recently mentioned in the conversation.

**"protect this directory"** / **"protect all files in src/engine/"**

Run: `kiri add src/engine/`

A trailing slash stores a `@glob` rule; all files inside are indexed automatically.
New files added to the directory are picked up within 60 seconds.

**"protect all Python files in src/"** / **"protect src/**/*.py"**

Run: `kiri add "src/**/*.py"`

**"protect the symbol @Foo"**

Run: `kiri add @Foo`

### Removing protection

**"remove protection from this file"** / **"unprotect"**

Run: `kiri rm <path>`

**"remove protection from this directory"** / **"unprotect src/engine/"**

Run: `kiri rm src/engine/`

Removes the `@glob` rule and purges all indexed vectors for files from that rule
(except files also individually listed in secrets).

**"remove symbol @Foo"**

Run: `kiri rm @Foo`

### Checking status

**"what is protected?"** / **"show kiri status"**

Run: `kiri status`

Output shows: protected directories/globs (with file count), individually protected
files, explicit symbols, number of indexed chunks and known symbols.

### Inspecting a prompt

**"would this prompt be blocked?"** / **"inspect this prompt"**

Run: `kiri inspect "<prompt>"`

Or, to avoid storing the prompt in shell history (recommended when the prompt
contains sensitive code):

```bash
kiri inspect --file prompt.txt
```

Add `--show-redacted` (or `-r`) to also print the full prompt as it would be
forwarded to the LLM when the decision is REDACT — the implementation is
replaced with a stub comment, everything else is preserved:

```bash
kiri inspect --show-redacted "explain calculate_final_price"
```

Output shows: Decision (PASS / BLOCK / REDACT), Reason, top similarity score,
matched symbols (if any), and — with `--show-redacted` on REDACT — the
complete forwarded prompt with protected code stripped.

### Managing protection summaries

When the gateway REDACTs a function, it replaces the body with an Ollama-generated
summary. Use these commands to inspect and correct what the LLM sees.

**"what does the LLM see for RiskScorer?"** / **"show the summary for calculate_final_price"**

Run: `kiri summary show <symbol>`

**"list all summaries"** / **"show me all redacted symbols"**

Run: `kiri summary list`

**"fix the summary for RiskScorer"** / **"set a custom description for calculate_final_price"**

Run: `kiri summary set <symbol> "<text>"`

Kiri warns if the text contains numeric literals that may reveal proprietary constants.
Manual summaries always take priority over Ollama-generated ones.

**"regenerate the summary for RiskScorer"** / **"reset to auto-generated"**

Run: `kiri summary reset <symbol>`

Removes the manual override and falls back to the Ollama-generated summary.
If no Ollama summary exists, re-generates it.

**"regenerate all summaries"**

Run: `kiri summary reset --all`

---

### Audit log

**"show blocked requests"** / **"who tried to exfiltrate?"**

Run: `kiri log --decision BLOCK`

**"show last N requests"**

Run: `kiri log --tail <N>`

**"show today's blocks"**

Run: `kiri log --decision BLOCK --since today`

Output shows: timestamp, decision, filter level (L1/L2/L3), reason, similarity score,
matched symbols, matched source file.

### Explaining why a request was filtered

**"why was that blocked?"** / **"explain last block"** / **"why was my request filtered?"** / **"what triggered the filter?"**

Run: `kiri explain`

**"explain the second last block"**

Run: `kiri explain --entry 2`

**"explain including passed requests"**

Run: `kiri explain --all`

**"show me the full message that was sent to the LLM"** / **"show the redacted prompt"** / **"cosa è stato mandato all'LLM?"**

Run: `kiri explain --show-redacted`

Output shows a plain-language breakdown: which filter level triggered, the similarity
score, the closest protected source file, the matched symbols, and the prompt excerpt
that caused the decision. With `--show-redacted`, also prints the complete prompt
as it was forwarded to the LLM (REDACT decisions only — protected function bodies
replaced with stub comments, everything else preserved).

### Key management

**"create a new kiri key"** / **"new key"**

Run: `kiri key create`

**"list kiri keys"** / **"show keys"**

Run: `kiri key list`

**"revoke key kr-..."**

Run: `kiri key revoke <key>`

### Indexing a file immediately

**"index this file now"**

Run: `kiri index <path>`

Use this when the kiri server is not running and you want to build the
embedding index immediately without waiting for the watcher.

---

## Secrets file format

`.kiri/secrets` is committed to git. It lists:

```
# paths relative to workspace root (one per line)
src/engine/risk_scorer.py
src/engine/token_bucket.py

# directory and glob rules (auto-expanded, 60 s rescan for new files)
@glob src/engine/
@glob src/**/*.pricing.*

# explicit symbols (immediate L2 protection, no indexing required)
@symbol RiskScorer
@symbol sliding_window
```

You can edit this file directly or use the CLI commands above.

---

## How the filter works

Every outgoing LLM call passes through three levels:

| Level | Check | Action |
|-------|-------|--------|
| L1 | Vector similarity ≥ 0.90 | REDACT |
| L1 | Vector similarity < 0.75 | PASS |
| L2 | Whole-word symbol match (always — even when L1/L3 unavailable) | REDACT |
| L3 | Ollama classifier, grace zone 0.75–0.90 | BLOCK if `extract_ip`, else REDACT |

A `REDACT` decision replaces protected function bodies with a stub comment before
forwarding — the prompt reaches the LLM but without the implementation details.

A `BLOCK` (HTTP 403) is returned only when L3 detects explicit intent to extract IP.

---

## Claude Pro / Max (OAuth passthrough)

If you use Claude Code with a Pro or Max subscription (no static API key),
enable OAuth passthrough mode in `.kiri/config.yaml`:

```yaml
oauth_passthrough: true
```

Then set only the base URL — do not set `ANTHROPIC_API_KEY`:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
```

Claude Code will continue using its own OAuth session. The gateway intercepts
every request, runs the full filter pipeline, and forwards with the original token.

> The dual-key bypass-prevention guarantee does not apply in this mode.
> See `docs/guides/claude-pro-max.md` for the full walkthrough.

---

## Setup

**One-time: store the real Anthropic key as a Docker secret**

```bash
mkdir -p .kiri
echo "sk-ant-YOUR-REAL-KEY" > .kiri/upstream.key
chmod 600 .kiri/upstream.key   # owner-read only
```

This file is gitignored. It is mounted inside the container at
`/run/secrets/anthropic_key` — it never appears in `docker inspect`
environment output or `docker exec env`.

**Start the gateway:**

```bash
docker compose up -d
```

**Set your Claude Code base URL (use direnv to avoid shell history leaks):**

```bash
cp .env.example .env
# edit .env — replace kr-your-key-here with your actual kr- key
echo "dotenv" >> .envrc
direnv allow
```

With direnv the variables are loaded automatically on `cd` — the key never
appears in shell history. Without direnv: `source .env` (do NOT use
`export ANTHROPIC_API_KEY=kr-...` directly — it ends up in `.bash_history`).

**Generate a kiri key:**

```bash
kiri key create
# or, if running only inside Docker:
# docker compose exec kiri kiri key create
```

The real `ANTHROPIC_API_KEY` lives only inside the container as a Docker
secret and is never exposed to developers or committed to git.

---

### Identifying which key made a request

Every audit log entry includes `key_id` — the first 12 characters of the
`kr-` key that made the request. This lets you correlate audit events back
to a specific developer or token and revoke a compromised key:

```
{"timestamp":"...","decision":"BLOCK","key_id":"kr-Ab3Cd5Ef6G",...}
```

---

### Installing the pre-commit hook

The repository ships a hook that prevents accidentally committing `kr-` keys:

```bash
bash scripts/install-hooks.sh
```

Run this once after cloning. The hook scans staged diff lines for the
`kr-[A-Za-z0-9_-]{20,}` pattern and blocks the commit if found.

---

### If a kr- key was accidentally committed to git

The pre-commit hook blocks future commits, but a key already in history is
still visible via `git log -p`. Remove it with:

```bash
# Install: pip install git-filter-repo
git filter-repo --replace-text <(echo "kr-YOURKEY==>REDACTED")
git push --force-with-lease
```

Then revoke the key immediately: `kiri key revoke kr-YOURKEY`

---

### Security assumptions about config.yaml

`.kiri/config.yaml` is committed to git and treated as **trusted input**.
The values `ollama_base_url` and `openai_upstream_url` control where the
gateway sends classifier and API traffic. Anyone with write access to the
repository can redirect these to an attacker-controlled server.

Do not commit config files from untrusted sources. Validate config on
deploy if the repository is shared with untrusted contributors.

---

## Important notes

- `.kiri/secrets` — commit to git ✅
- `.kiri/config.yaml` — commit to git ✅
- `.kiri/index/` — do NOT commit (rebuilt locally) ❌
- `.kiri/keys/` — do NOT commit (per-developer) ❌

When you add a new file to secrets, the gateway automatically re-indexes it in
the background via the file watcher. You do not need to restart anything.
