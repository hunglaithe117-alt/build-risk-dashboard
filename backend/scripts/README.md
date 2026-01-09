# Git History Reconstructor - Demo Script

This script replays commits from a source repository to a target repository while monitoring GitHub Actions CI status. It is designed for demoing the **Build Risk Dashboard** pipeline.

## Purpose

- Replay commits from an existing repository to a new repository
- Preserve original commit metadata (author, timestamp, message)
- Filter workflows to keep only test-related jobs
- Monitor GitHub Actions status for each commit

## Prerequisites

1. **Python 3.11+**
2. **GitHub Personal Access Token** with `repo` and `workflow` permissions
3. **Source Repository** (local clone of a repo you want to replay)
4. **Target Repository** (empty repo on GitHub where commits will be pushed)

## Setup

1. Install dependencies (managed by backend's `pyproject.toml`):
   ```bash
   cd backend
   uv pip install -e .
   ```

2. Configure environment:
   ```bash
   cd backend/scripts
   cp .env.example .env
   # Edit .env with your values
   ```

3. Clone your source repository locally:
   ```bash
   git clone https://github.com/original-owner/source-repo.git /path/to/source
   ```

4. Create and clone an empty target repository:
   ```bash
   # Create empty repo on GitHub first
   git clone https://github.com/your-org/target-repo.git /path/to/target
   ```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | Personal Access Token with repo/workflow permissions | ✅ |
| `REPO_FULL_NAME` | Target repository (e.g., `your-org/target-repo`) | ✅ |
| `SOURCE_REPO_PATH` | Absolute path to local source repo | ✅ |
| `TARGET_REPO_PATH` | Absolute path to local target repo | ✅ |
| `LIMIT_COMMITS` | Number of recent commits to replay (0 = all) | ❌ |
| `POLL_INTERVAL` | Seconds between CI status checks (default: 30) | ❌ |
| `WORKFLOW_TIMEOUT` | Max seconds to wait for CI (default: 600) | ❌ |

## Usage

```bash
cd backend/scripts
python main.py
```

The script will:
1. Iterate through commits in topological order
2. For each commit:
   - Copy files to target repo
   - Filter workflow files (remove bots, secrets, non-test jobs)
   - Create commit preserving original metadata
   - Push to target
   - Wait for GitHub Actions (with timeout)
3. Track progress in `state.db` (SQLite)

## Workflow Filtering

The script automatically filters GitHub Actions workflows:

**Kept jobs** (whitelist keywords):
- test, lint, check, build, ci, validate, verify, unit, integration, format, style

**Removed jobs**:
- Bot-related (dependabot, renovate, snyk, etc.)
- Deployment/Release (deploy, publish, release, push, upload, registry, docker, npm, pypi, pages)
- Notifications (notify, slack, discord, email)
- Scheduled jobs (schedule, cron)
- Jobs using secrets
- Jobs not matching test keywords

## State Tracking

Progress is tracked in `state.db`. If the script is interrupted:
- Re-run to resume from the last successful commit
- Delete `state.db` to start fresh

## Example Demo Flow

1. **Prepare**: Set up source/target repos and configure `.env`
2. **Run**: Execute `python main.py`
3. **Import**: In Build Risk Dashboard, import the target repository
4. **Observe**: Watch the pipeline process builds as commits are pushed
5. **Demo**: Show real-time predictions as new commits arrive

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Script hangs | Check `WORKFLOW_TIMEOUT`, ensure repo has valid workflows |
| Auth errors | Verify `GITHUB_TOKEN` has correct permissions |
| Missing workflows | Script skips CI wait if no workflows exist |
| Resume issues | Delete `state.db` to start fresh |
