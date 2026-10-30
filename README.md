# Restore Chat Context for Codex

A Codex Desktop skill for continuing a named chat in a new chat: recover its latest saved compaction, preserve retained messages, and read every available record after the checkpoint.

**Recommended host model: Luna.** It is sufficient for routine context transfer and provides economical token usage. This recommendation concerns the chat reading and reconciling history. The recovery helper uses the original checkpoint model for compatibility; it does not silently replace that model with Luna. Lower model cost does not guarantee fewer input tokens.

## Install

Requirements: Windows, Codex Desktop with a signed-in account and local session files, Python 3.11+, and Node.js 18+. Compressed `.jsonl.zst` archives additionally require `zstandard` (`python -m pip install zstandard`).

Install into the default skills directory using PowerShell:

```powershell
git clone https://github.com/gj9159a/codex-restore-chat-context.git "$env:USERPROFILE\.codex\skills\restore-chat-context"
```

For a custom `CODEX_HOME`, use its `skills/restore-chat-context` directory instead. Start a new chat after installation. If the destination already exists, update your checkout instead of overwriting an unrelated installation.

## Use

Choose Luna for the new chat and provide the exact full source title:

```text
$restore-chat-context Recover the latest compaction and the complete subsequent history of the chat titled "Full title of the old chat" into this chat.
```

The skill resolves duplicate titles with you, snapshots the source, resumes a separate recovery copy, checks reopening, and reads the continuation in ordered pages. It maintains working notes and verifies page receipts, file integrity, source changes, and known gaps before claiming complete coverage. Source files remain unchanged. Recovery requests consume the ordinary model allowance.

Full operating instructions are in [SKILL.md](SKILL.md). Helpers also support command-line usage:

```powershell
python -X utf8 scripts/transfer.py --help
node scripts/recover.cjs --bundle 'C:\absolute\path\to\bundle' --verify-resume
```

Create a bundle as described in the skill before running recovery.

## What is preserved

- The latest checkpoint and its retained messages.
- Other retained checkpoint records, including tool results, exported for required reading.
- All available continuation records: messages, tool calls, outputs, errors, and administrative events.
- Raw snapshots, hashes, reading receipts, a semantic review receipt, and explicit coverage boundaries.

Historical commands are treated as data and are not automatically executed. Recovery uses a read-only sandbox, disables ordinary execution/search capabilities, rejects unexpected tool requests, and terminates on errors or timeouts.

## Limits

This experimental technique uses the local Codex app-server protocol. It was exercised against managed runtime `0.166.0-alpha.5.1`; compatibility with future releases is not guaranteed. Executable discovery currently targets Windows, and source chats must be local.

Compaction is already a compressed representation of earlier history, not a verbatim transcript. Missing attachments, previously truncated results, an unknown source model, or an injected standalone block without its retained history prevent an unqualified completeness claim. Hidden reasoning remains opaque. A successful request alone is insufficient: the reviewing agent must verify concrete recovered facts.

Recovered bundles contain private conversation data. They stay under the local Codex temporary directory and must not be committed or uploaded with this repository. This repository contains no conversation exports or recovered user context.

## Tests and validation

```powershell
python -B -X utf8 -m unittest discover -s scripts -p test_transfer.py -v
node --test scripts/test_recover.cjs
```

The suite includes 18 Python tests and 15 Node tests. Tests use synthetic history and local mock app-server processes and require no OpenAI or GitHub API calls. Real local checkpoint recovery and reopening were additionally exercised during development. A large source continuation was exported losslessly; its full manual reading was not completed in that validation run. Complete page reading was exercised on a smaller real continuation.
