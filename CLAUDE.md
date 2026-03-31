# XiaomiPurifier

## Project Overview
Token extraction and WiFi provisioning tools for 7 Xiaomi air purifiers. Pivoted from custom Flask app to Home Assistant on Raspberry Pi 5. The Flask app (app.py) is archived; the active tools are extract_tokens.py and provision_china.py.

## Key Files
- `extract_tokens.py` — Cloud token extraction with 2FA support
- `provision_china.py` — Raw miio WiFi provisioner for China-set devices
- `tokens_extracted.json` — Extracted tokens (gitignored, contains secrets)
- `china_provision_result.json` — Provisioning results (gitignored)
- `app.py` — Archived Flask dashboard
- `discover.py` — Network discovery tool

## Crash Recovery (two-signal checkpoint protocol)

CHECKPOINT.md in the memory directory is a live state file that persists across conversations.

### Session start (ALWAYS do this):
1. Read CHECKPOINT.md
2. Run `git diff --stat HEAD` and `git log --oneline -3`
3. Determine crash state using BOTH signals:

| CHECKPOINT | Uncommitted changes? | Verdict |
|------------|---------------------|---------|
| ACTIVE | Yes or No | Definite crash — CHECKPOINT has what/where/progress. Tell user what was in progress, what's done, what's left. Check `.claude/plans/` for in-progress plan files. If CHECKPOINT has a Plan File path, read that file for full context. Offer to resume or start fresh. |
| IDLE | Yes (dirty working tree) | Probable crash — another session started work but crashed before checkpointing. Show `git diff --stat`, recent log, and any `.claude/plans/*.md` modified in last 24h. Ask user: "I see uncommitted changes — was this from a crashed session? Want me to pick up where it left off?" |
| IDLE | No (clean tree) | No crash — proceed normally. |

**Critical:** Never skip Step 2. CHECKPOINT alone is not reliable — sessions can crash before setting ACTIVE.

**Note:** CHECKPOINT.md lives in the memory directory, outside the git repo. `git status` will never reflect checkpoint changes — always read the file directly.

### When to checkpoint (set ACTIVE):
- At session start whenever the user's first message implies work (not just questions). Use minimal format:

```markdown
# Session Checkpoint
**State**: ACTIVE
**Updated**: YYYY-MM-DD
**Plan File**: (path to active .claude/plans/*.md, or "none")
**Resume Point**: (not yet started)
**Started**: User's first message (summarized)
**What's Done**: (nothing yet)
**What's Left**: (to be determined)
```

- Before any risky operation (large refactor, API calls with side effects)
- Do NOT checkpoint trivial tasks (quick questions, single reads, one-line edits)

### ACTIVE checkpoint format (enriched during work):

```markdown
# Session Checkpoint
**State**: ACTIVE
**Task**: (1-line summary of what user asked for)
**Updated**: (date + time)
**Plan File**: (path to active .claude/plans/*.md, or "none")
**Resume Point**: (exact position to resume from)

## What's Done
- (completed step with file paths)

## What's Left
- (remaining steps)

## Key Decisions Made
- (any choices or context future sessions need)

## Files Modified
- (list of changed files)
```

### During multi-step work:
- Update "What's Done", "What's Left", and "Resume Point" after each completed step
- Update before risky operations (so crash = recovery possible)
- Keep it concise — this is a resume point, not a log

### Session end (normal):
- Set state back to IDLE (minimal format — just state + date + "No active work")
- If the project has STATUS.md, update it with session summary

### Staleness rule:
If CHECKPOINT.md says ACTIVE but "What's Done" is empty AND no uncommitted changes exist, it's stale — discard and proceed normally. Otherwise, trust the checkpoint even if it's days old. Fall back to `git diff` and `git log` for additional recovery evidence.
