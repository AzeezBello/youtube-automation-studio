# Compliance, Privacy & Data Governance Architecture

YouTube Automation Studio is architected from the ground up to enforce **YouTube API Services Terms of Service**, creator data sovereignty, and strict intellectual-property hygiene.

---

## 1. 100% Manual Publishing Control (No Automated Uploads)

By design, YouTube Automation Studio **never** holds OAuth upload tokens or performs automated background video publishing:
- All production pipelines terminate at a local **Export Package** (`package_manifest.json`, `.mp4`, `.png` thumbnail, `.srt` subtitles, and copy-ready description/chapters).
- The creator inspects, reviews, and manually uploads the final video via YouTube Studio in their browser.
- `ComplianceReviewGate` verifies `manual_publish_only` on every export manifest and rejects any manifest containing automated upload flags (`auto_upload`, `oauth_upload_token`, `scheduled_remote_publish`).

---

## 2. YouTube Data API v3 — 30-Day Cache Retention Policy

All public metadata fetched from the YouTube Data API v3 (`videos.list`, `search.list`, `channels.list`) is tagged at ingestion time with:
- `source_class = "public_api_30d"`
- `fetched_at` (UTC timestamp)
- `expires_at = fetched_at + 30 days`

### Automated & On-Demand Expiration Enforcement
1. **`RetentionPolicy`** (`src/youtube_studio/domain/policies/retention.py`) computes exact UTC expiration windows and flags any record older than 30 days.
2. **`RetentionJobRunner`** (`src/youtube_studio/jobs/retention_runner.py`) purges expired `ResearchSnapshot` rows from SQLite automatically and can be triggered at any time from **Settings → Purge Expired 30d API Cache**.
3. **`ComplianceReviewGate`** checks all `research_sources` referenced in an export manifest and fails the compliance gate if any `public_api_30d` snapshot is older than 30 days.

---

## 3. Prohibition on Derived Competitor Scores

In accordance with YouTube API Services policies regarding scraping and undocumented derived metrics:
- YouTube Automation Studio **only** stores raw public API fields (`viewCount`, `likeCount`, `commentCount`, `publishedAt`, `title`, `tags`) during their 30-day cache window.
- It **never** computes, stores, or exports proprietary cross-channel derived scores (`competitor_score`, `viral_velocity_index`, `vidiq_score`, `engagement_rank_percentile`, `scraped_html_payload`, `unofficial_dislike_estimate`).
- `ComplianceReviewGate` recursively inspects every export manifest and fails immediately if any prohibited derived metric key is present.

---

## 4. Credential Vault Isolation

- API keys are managed exclusively via `CredentialVault` (`src/youtube_studio/security/vault.py`), which prioritizes the native OS Keychain (`macOS Keychain` / `Windows Credential Manager` via `keyring`) with an PBKDF2/XOR-obfuscated `0600`-permissioned local vault fallback.
- Database backups created by `BackupService` (`src/youtube_studio/storage/backup.py`) snapshot the SQLite database and non-secret application settings while **excluding** raw credential vault secrets.

---

## 5. Pre-Release Compliance Review Gate Checklist

Before a release package is marked ready, `ComplianceReviewGate.review_package_manifest()` runs five automated checks:

| Check ID | Category | Rule Enforced |
| :--- | :--- | :--- |
| `manual_publish_only` | `manual_control` | Confirms no automated upload tokens or background publishing triggers exist. |
| `no_prohibited_derived_metrics` | `api_compliance` | Ensures zero prohibited scraped or third-party derived metric keys exist in the manifest. |
| `api_30d_retention_freshness` | `api_compliance` | Verifies every `public_api_30d` research snapshot is `< 30` days old. |
| `youtube_metadata_limits` | `metadata_policy` | Validates title length (`1..100` chars), description (`<= 5000` chars), tags (`<= 500` chars), and chronological chapters starting at `00:00`. |
| `media_outputs_verified` | `media_integrity` | Verifies rendered video and thumbnail files exist on disk and are non-empty. |
