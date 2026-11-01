# Codex Chat Context Recovery — Continue, Transfer, and Restore Chats

**Continue a long Codex Desktop chat in a new chat, recover context from a frozen conversation, and carry forward decisions, constraints, and unfinished tasks.** This Windows skill recovers the latest native compaction checkpoint and reads the complete available history after it, including tool calls, results, and errors.

Also useful for **Codex session recovery**, **chat-to-chat context transfer**, **conversation handoff**, and **context restoration after a chat error**. You provide the exact source chat title; the skill prepares readable working context for the new chat while leaving source files unchanged.

[Install](#install) · [Quick start](#quick-start) · [Use cases](#when-to-use-this-skill) · [FAQ](#frequently-asked-questions) · [Agent instructions](SKILL.md) · [Latest release](https://github.com/gj9159a/codex-restore-chat-context/releases/latest)

**Recommended host model: Luna.** It is sufficient for routine history reading and reconciliation and offers economical token usage. The recovery helper still uses the original checkpoint model for compatibility. Lower model cost does not guarantee fewer input tokens.

## When to use this skill

| Your problem | What the skill does |
|---|---|
| A long Codex chat has become difficult to continue | Recovers its saved context into a new chat and reads the subsequent history |
| A local conversation is frozen or fails when you send a message | Reads local session files without opening the frozen UI; uses a separate recovery copy |
| You want to move work between chats without losing decisions | Carries forward constraints, decisions and reasons, verified results, and unfinished tasks |
| You need more than a summary of the last few messages | Starts at the latest checkpoint and reads every available continuation page |
| A coding agent needs a reliable handoff from an earlier session | Produces readable working notes with source identity, coverage boundaries, and explicit gaps |
| Native compaction is stored as an opaque encrypted block | Resumes a separate copy through the local app-server instead of treating ciphertext as readable text |

**Scope:** local Codex Desktop sessions on Windows. This is an independent community tool, not an official OpenAI feature. It does not import ordinary ChatGPT web/mobile chats, synchronize computers or accounts, repair the original chat, or provide a lossless pre-compaction transcript.

## Install

Requirements:

- Codex Desktop on Windows, signed in, with local source session files and chat-listing tools available to the agent.
- Python 3.11+ and Node.js 18+ available on `PATH`.
- Optional `zstandard` for compressed `.jsonl.zst` archives: `python -m pip install zstandard`.

Install into the default skills directory in PowerShell:

```powershell
git clone https://github.com/gj9159a/codex-restore-chat-context.git "$env:USERPROFILE\.codex\skills\restore-chat-context"
```

For a custom `CODEX_HOME`, use its `skills/restore-chat-context` directory. Start a new chat after installation. If that directory already exists, update the existing checkout rather than overwrite an unrelated installation.

## Quick start

Choose Luna in a new Codex chat and provide the **exact full title** of the source:

```text
$restore-chat-context Continue my chat titled "Full title of the old chat" here. Recover its latest saved compaction and read everything after it, including tool results and errors. Preserve decisions, constraints, and unfinished tasks, and report any gaps.
```

The workflow asks you to choose only if titles are ambiguous. It creates a local bundle, checks checkpoint recovery and reopening, reads the continuation, and records progress so it can resume after interruption. Recovery requests consume the ordinary model allowance.

The result is `working-context.md` plus an explicit report of what was recovered and read. A technically successful request alone is not enough to claim complete coverage.

## How native compaction recovery works

```text
Exact source chat title
  -> resolve local rollout and take an unchanged-source snapshot
  -> extract latest native checkpoint plus retained messages
  -> resume a separate legacy recovery copy with the source model
  -> check concrete recovered facts and reopening
  -> read retained supplemental records and the entire continuation
  -> verify receipts, hashes, source changes, and known gaps
  -> continue in the new chat with readable working context
```

The helper uses `thread/resume` with a separate local rollout. It does not inject a compaction item into your active chat, edit the source database, or execute historical commands. The new chat receives **readable context reconstructed from the native checkpoint**, not the encrypted block as its own internal state.

Preserved material includes retained user messages, retained tool results exported for reading, all available post-compaction messages and tool events, errors, and administrative records. The raw snapshots retain data that is opaque or unsuitable for ordinary text display.

## Frequently asked questions

### How do I continue a long Codex chat in a new chat?

Install the skill, open a new local Codex chat, and invoke `$restore-chat-context` with the exact old title. It recovers the saved checkpoint and reads the full available continuation before handing back working context.

### Can I transfer native compaction between Codex Desktop chats?

The skill reuses the saved native checkpoint in a **separate recovery session**, then transfers its meaning as readable context. It also preserves retained messages and reads everything after the checkpoint. It does not promise direct encrypted-state insertion into the destination chat.

### Can I recover context from a frozen or broken conversation?

Yes, when the local rollout and a usable checkpoint or readable history remain available. The source UI need not open. Missing or corrupt source data is reported rather than silently skipped. Recovering context does not repair the broken conversation itself.

### Does it preserve decisions, tasks, and tool outputs?

The workflow reads available messages, tool calls, results, errors, and retained checkpoint supplements. Working notes distinguish current decisions from superseded ones, attempted actions from verified results, and unfinished tasks from completed work.

### What if the source chat has never compacted?

The helper exports the complete available history for ordered reading. No encrypted checkpoint recovery is needed.

### Is this a lossless conversation export or a replacement for backup?

No. Compaction has already compressed earlier history. The skill retains source snapshots and reads all available continuation, but cannot recreate every earlier sentence, missing attachment, already-truncated result, or hidden reasoning. Known gaps prevent an unqualified completeness claim.

### Does it support ChatGPT Desktop, the website, or mobile chats?

It supports **local Codex session files**. Searching for ChatGPT Desktop conversation recovery may lead here, but ordinary ChatGPT web/mobile chat history is outside this tool's scope. The actual local Codex storage and managed runtime are required.

### Can an agent use this automatically?

An installed skill can be invoked by name or selected when its description matches the request. Use [SKILL.md](SKILL.md) for the operating procedure and [llms.txt](llms.txt) for a short document index. These files help an agent understand this repository after discovery; they do not guarantee inclusion in web search or model answers.

### Which model should I use?

Luna is recommended for the host chat reading and reconciling the history. The checkpoint recovery subprocess must preserve the source model; unknown or mismatched models stop recovery instead of being guessed.

## Compatibility, privacy, and failure handling

The local app-server interface is experimental. Recovery and reopening were exercised against managed runtime `0.166.0-alpha.5.1`; future compatibility is not guaranteed. Executable discovery currently targets Windows. Cross-account and cross-computer migration are not supported workflows.

The recovery subprocess uses a read-only sandbox, disables ordinary execution/search capabilities, rejects unexpected tool requests, and terminates on errors or timeout. The reviewing agent must inspect the actual response and record specific evidence of meaningful recovery.

Private conversation bundles stay under the local Codex temporary directory. Do not commit or upload them with the repository. The published source and tests contain no real chat exports or recovered private context.

## Tests and verification

```powershell
python -B -X utf8 -m unittest discover -s scripts -p test_transfer.py -v
node --test scripts/test_recover.cjs
```

There are **33 automated tests: 18 Python and 15 Node**. They use synthetic history and local mock app-server processes, without OpenAI or GitHub API calls. They cover checkpoint selection, retained records, large outputs, compressed archives, parent segments, source changes, reading receipts, semantic confirmation, model mismatches, failures, timeouts, and subprocess shutdown.

Real checkpoint recovery and reopening were also exercised during development. A large continuation was exported losslessly, but its full manual reading was not completed in that validation run. Complete page reading was exercised on a smaller real continuation. The instructions are English; a new live recovery run has not been repeated solely to validate the prompt translation.

For reproducible bug reports, include the runtime version, operating system, error code, and redacted coverage report. Do not attach raw conversation bundles, encrypted compaction data, credentials, or private tool output. [Report an issue](https://github.com/gj9159a/codex-restore-chat-context/issues).
