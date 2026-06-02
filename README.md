# itential-trigger

A minimal Python CLI for triggering [Itential Operations Manager](https://www.itential.com/) workflows over the API. Point it at a trigger route, optionally hand it a JSON payload, and it fires a POST — fire-and-forget by default, or block and poll until the job finishes.

## Requirements

- Python 3.11+
- An Itential platform with an Operations Manager endpoint trigger configured

## Install

```bash
pip install -r requirements.txt
```

Dependencies: `ipsdk>=0.7.0`, `python-dotenv>=1.0.0`

## Configuration

Credentials and connection settings are read from a `.env` file in the working directory. Set **one** of the two auth blocks — the tool auto-detects which one you've provided.

```
# Required
ITENTIAL_HOST=your-platform.example.com

# Auth — set ONE of the two blocks

# Option A: OAuth (client credentials)
ITENTIAL_CLIENT_ID=your-client-id
ITENTIAL_CLIENT_SECRET=your-client-secret

# Option B: Basic auth
# ITENTIAL_USER=your-username
# ITENTIAL_PASSWORD=your-password

# Optional (defaults shown)
ITENTIAL_PORT=443
ITENTIAL_USE_TLS=true
ITENTIAL_VERIFY_TLS=true
ITENTIAL_TIMEOUT=30
```

If both auth blocks are present, the tool exits with an error — set only one.

## Usage

```bash
python trigger_workflow.py <trigger_name> [json_payload] [options]
```

The tool POSTs to `/operations-manager/triggers/endpoint/{trigger_name}`.

```bash
# Fire and forget
python trigger_workflow.py my-route

# With payload
python trigger_workflow.py my-route '{"device": "router1"}'

# Complex payload
python trigger_workflow.py my-route '{"devices": [{"name": "r1", "ip": "10.0.0.1"}], "options": {"dry_run": false}}'

# Block until complete (polls every 3s by default)
python trigger_workflow.py my-route '{"device": "router1"}' --wait

# Custom poll interval
python trigger_workflow.py my-route '{"device": "router1"}' --wait --poll-interval 5
```

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--wait` | Block and poll until the job reaches a terminal status (`complete`, `error`, `cancelled`). Prints status on each tick. | off |
| `--poll-interval <seconds>` | How often to poll for status when using `--wait`. | `10` |

## Behavior

- **Default (fire-and-forget):** the trigger fires and the tool returns immediately with the job response.
- **With `--wait`:** the tool blocks, polling job status at the configured interval and printing each update, until the job completes, errors, or is cancelled.
