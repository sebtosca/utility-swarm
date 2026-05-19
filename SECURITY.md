# Security

## API keys

Your Anthropic API key is stored only in `~/.cjs/config.yaml` — your user home directory,
never inside the repository. The `.gitignore` covers `config.yaml`, `runs/`, and `my_runs/`.
Do not commit these files.

## Local-only data

Video files and brief PDFs are never uploaded to any third-party service. All processing
is local: ffmpeg and Whisper run on your machine. Frames and transcripts are sent directly
to Anthropic's API under your own API key, subject to Anthropic's data handling policies.
No data passes through any CJS-operated server.

## Audit trail

Every LLM call is logged to `runs/<run_id>/audit.jsonl`. Each entry contains the model,
node name, token counts, latency, and a SHA-256 hash of the rendered prompt — not the raw
prompt text. This provides a verifiable record of what was called and when, without storing
sensitive brief or video content in plaintext logs.

## Reporting a vulnerability

Open a GitHub Security Advisory (preferred for vulnerabilities with working exploits) or
a GitHub issue labelled `security` for lower-severity findings. Do not include exploit
details in a public issue. We will acknowledge within 48 hours and coordinate a fix before
any public disclosure.
