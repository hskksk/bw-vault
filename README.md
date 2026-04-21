# bw-vault

Bitwarden vault secrets injector. Fetches secrets from Bitwarden and injects them as environment variables, with transparent caching via [cli-cache](https://github.com/hskksk/cli-cache).

## Installation

```bash
uv tool install git+https://github.com/hskksk/bw-vault
```

Requires `bw` (Bitwarden CLI) and `age` to be on your PATH.

## Configuration

Create `~/.config/bw-vault/config.toml` (or `$XDG_CONFIG_HOME/bw-vault/config.toml`):

```toml
[default]
OPENAI_API_KEY = "OpenAI API:api-key"
LINEAR_API_KEY = "Linear:api-key"

[work]
DB_PASSWORD = "Production DB:password"
STRIPE_KEY  = "Stripe:api-key"
```

Each entry maps an environment variable name to a Bitwarden item and field in the form `"Item Name:field"`.

**Built-in fields:** `username`, `password`, `totp`, `notes`, `uri`

**Custom fields:** any other string matches a custom field by name in the Bitwarden item.

### Master password

bw-vault expects the Bitwarden master password encrypted with age at `~/.bw_pass.age`:

```bash
echo "your-master-password" | age -r "$(cat ~/.ssh/id_ed25519.pub)" > ~/.bw_pass.age
```

## Usage

### `exec` — inject secrets into a command

```bash
# Open a shell with secrets from the [default] profile
bw-vault exec

# Run a command with secrets from the [default] profile
bw-vault exec -- some-command --flag

# Use a named profile
bw-vault exec work -- some-command

# Named profile with arguments
bw-vault exec work -- printenv DB_PASSWORD
```

### `run` — run a command with BW_SESSION set

```bash
bw-vault run bw list items
```

Ensures the Bitwarden session is unlocked and sets `BW_SESSION` in the environment before executing the command. Useful for running `bw` commands directly.

## How it works

bw-vault implements a two-layer session/cache state machine:

```
Request
  │
  ▼
[cli-cache session valid? (t2)]
  │
  ├─ No  → clear cache → [BW session check]
  │
  └─ Yes → check each item in cache
              │
              ├─ All cached  → return immediately (no network calls)
              │
              └─ Any missing → [BW session check]
                                  │
                                  ├─ BW session valid (t1) ──┐
                                  │                          │
                                  └─ Expired → age decrypt   │
                                             → bw unlock ────┘
                                                    │
                                                    ▼
                                             fetch from BW → update cache
```

- **t2** (cli-cache session TTL, default 24h): controls how long the encrypted cache is trusted. On expiry, the entire cache is cleared and re-fetched.
- **t1** (Bitwarden session TTL): controlled by `bw unlock`. If the BW session token stored in `$XDG_STATE_HOME/bw-vault/session` is no longer valid, the vault is re-unlocked via the age-encrypted master password.

On a full cache hit, bw-vault makes zero subprocess calls to `bw`.

## Development

```bash
git clone https://github.com/hskksk/bw-vault
cd bw-vault
mise use uv
uv sync --group dev
uv run pytest
```
