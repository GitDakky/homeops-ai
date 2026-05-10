#!/usr/bin/env bash
set -euo pipefail

# Ensure Homebrew and brew-installed binaries are in PATH
# This is needed for Hermes skills that depend on CLI tools (gemini, aider, etc.)
export PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"

# Home Assistant add-on options are usually rendered to /data/options.json
OPTIONS_FILE="/data/options.json"
LEGACY_ADDON_SLUG="homeops_ai"
SELF_ADDON_NAME="HomeOps AI"
MIGRATION_FLAG="/config/.gitdakky-legacy-migration"
MIGRATED_OPTIONS_FILE="/tmp/homeops-ai-options.json"
DEFAULT_TERMINAL_PORT="7682"
DEFAULT_GATEWAY_PORT="18790"
DEFAULT_INGRESS_PORT="48109"
DEFAULT_DASHBOARD_API_PORT="48110"
BOOTSTRAP_SOURCE_DIR="/opt/homeops-ai/bootstrap-workspace"
BUNDLED_SKILLS_SOURCE_DIR="/opt/homeops-ai/bundled-skills"
HERMES_CONFIG_PATH="/config/.hermes/config.yaml"
HOME_ASSISTANT_CONFIG_DIR="${HOME_ASSISTANT_CONFIG_DIR:-/ha-config}"
RUNTIME_RESTART_REQUEST_FILE="/tmp/hermes-runtime-restart.request"
MANAGED_COMMAND_ACTIVE_FILE="/tmp/hermes-managed-command.active"
RUNTIME_WRAPPER_LOG_DIR="/tmp/hermes"
RUNTIME_WRAPPER_LOG_FILE="${RUNTIME_WRAPPER_LOG_DIR}/homeops-ai-runtime-wrapper.log"
RUN_HELPERS_PATH="/opt/homeops-ai/run_helpers.sh"

if [ -f "$RUN_HELPERS_PATH" ]; then
  # shellcheck source=/dev/null
  . "$RUN_HELPERS_PATH"
fi

if [ ! -f "$OPTIONS_FILE" ]; then
  echo "Missing $OPTIONS_FILE (add-on options)."
  exit 1
fi

supervisor_api() {
  local method="$1"
  local path="$2"
  shift 2

  if [ -z "${SUPERVISOR_TOKEN:-}" ]; then
    return 1
  fi

  curl -fsSL -X "$method" \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor${path}" \
    "$@"
}

maybe_migrate_legacy_addon() {
  local legacy_addons_json legacy_slug legacy_repo legacy_ref legacy_dir legacy_info legacy_name legacy_state
  local legacy_options_json stop_ok=false
  local migration_precheck
  migration_precheck="$(legacy_migration_precheck "$MIGRATION_FLAG" /config "${SUPERVISOR_TOKEN:-}" /addon_configs)"
  case "$migration_precheck" in
    already-evaluated)
      echo "INFO: Legacy migration already evaluated for this install."
      return 0
      ;;
    skipped-existing)
      echo "INFO: Existing ${SELF_ADDON_NAME} state detected; skipping legacy migration."
      printf 'skipped-existing\n' > "$MIGRATION_FLAG"
      return 0
      ;;
    skipped-no-supervisor)
      echo "INFO: Supervisor API unavailable; skipping legacy migration."
      return 0
      ;;
    skipped-no-addon-configs)
      echo "INFO: /addon_configs is not mounted; skipping legacy migration."
      return 0
      ;;
  esac

  legacy_addons_json="$(supervisor_api GET /addons 2>/dev/null || true)"
  if [ -z "$legacy_addons_json" ]; then
    echo "INFO: Could not query installed add-ons; skipping legacy migration."
    return 0
  fi

  legacy_slug="$(printf '%s' "$legacy_addons_json" | jq -r '
    .data.addons[]?
    | (.slug // empty)
    | select(. == "homeops_ai" or endswith("_homeops_ai"))
  ' | head -n1)"

  legacy_repo="$(printf '%s' "$legacy_addons_json" | jq -r '
    .data.addons[]?
    | select((.slug // "") == "homeops_ai" or ((.slug // "") | endswith("_homeops_ai")))
    | (.repository // empty)
  ' | head -n1)"

  if [ -z "$legacy_slug" ] && [ -z "$legacy_repo" ]; then
    echo "INFO: No legacy HomeOps AI install detected."
    return 0
  fi

  if [ -z "$legacy_slug" ]; then
    legacy_slug="$LEGACY_ADDON_SLUG"
  fi

  if [ -z "$legacy_repo" ] && [[ "$legacy_slug" == *"_${LEGACY_ADDON_SLUG}" ]]; then
    legacy_repo="${legacy_slug%_${LEGACY_ADDON_SLUG}}"
  fi

  if [ "$legacy_slug" = "$LEGACY_ADDON_SLUG" ] && [ -n "$legacy_repo" ]; then
    legacy_ref="${legacy_repo}_${LEGACY_ADDON_SLUG}"
  else
    legacy_ref="$legacy_slug"
  fi

  legacy_dir=""
  if [ -n "$legacy_repo" ]; then
    legacy_dir="/addon_configs/${legacy_repo}_${LEGACY_ADDON_SLUG}"
  else
    legacy_dir="$(find /addon_configs -maxdepth 1 -type d -name "*_${LEGACY_ADDON_SLUG}" | head -n1)"
  fi

  if [ -z "$legacy_dir" ] || [ ! -d "$legacy_dir" ]; then
    echo "INFO: Legacy add-on was detected via Supervisor API but its config directory was not found."
    printf 'skipped-no-config\n' > "$MIGRATION_FLAG"
    return 0
  fi

  legacy_info="$(supervisor_api GET "/addons/${legacy_ref}/info" 2>/dev/null || true)"
  if [ -z "$legacy_info" ] && [ "$legacy_ref" != "$LEGACY_ADDON_SLUG" ]; then
    legacy_info="$(supervisor_api GET "/addons/${LEGACY_ADDON_SLUG}/info" 2>/dev/null || true)"
  fi

  legacy_name="$(printf '%s' "$legacy_info" | jq -r '.data.name // "HomeOps AI"' 2>/dev/null || echo "HomeOps AI")"
  legacy_state="$(printf '%s' "$legacy_info" | jq -r '.data.state // empty' 2>/dev/null || true)"
  legacy_options_json="$(printf '%s' "$legacy_info" | jq -c '.data.options // {}' 2>/dev/null || echo '{}')"

  if [ "$legacy_state" = "started" ] || [ "$legacy_state" = "startup" ]; then
    echo "INFO: Stopping legacy add-on '${legacy_name}' (${legacy_ref}) before migration..."
    if supervisor_api POST "/addons/${legacy_ref}/stop" >/dev/null 2>&1 || \
       supervisor_api POST "/addons/${LEGACY_ADDON_SLUG}/stop" >/dev/null 2>&1; then
      stop_ok=true
      echo "INFO: Legacy add-on stopped successfully."
    else
      echo "WARN: Could not stop the legacy add-on automatically. Port conflicts may still occur."
    fi
  fi

  echo "INFO: Importing legacy add-on data from ${legacy_dir} ..."
  mkdir -p /config
  rsync -a "${legacy_dir}/" /config/

  if [ -n "$legacy_options_json" ] && [ "$legacy_options_json" != "{}" ]; then
    printf '%s\n' "$legacy_options_json" > "$MIGRATED_OPTIONS_FILE"
    supervisor_api POST /addons/self/options \
      --data "$(jq -cn --argjson options "$legacy_options_json" '{options: $options}')" >/dev/null 2>&1 || \
      echo "WARN: Could not persist migrated add-on options to Supervisor; current boot will still use them."
    OPTIONS_FILE="$MIGRATED_OPTIONS_FILE"
  fi

  {
    echo "source=${legacy_ref}"
    echo "stopped=${stop_ok}"
    echo "imported=true"
  } > "$MIGRATION_FLAG"

  echo "INFO: Legacy migration completed from '${legacy_name}'."
}

maybe_migrate_legacy_addon

# ------------------------------------------------------------------------------
# Read add-on options (only add-on-specific knobs; Hermes is configured via onboarding)
# ------------------------------------------------------------------------------

TZNAME=$(jq -r '.timezone // "Europe/Sofia"' "$OPTIONS_FILE")
LLM_PROVIDER=$(jq -r '.llm_provider // "openrouter"' "$OPTIONS_FILE")
LLM_MODEL=$(jq -r '.llm_model // "openai/gpt-5.5"' "$OPTIONS_FILE")
OPENROUTER_API_KEY_OPTION=$(jq -r '.openrouter_api_key // empty' "$OPTIONS_FILE")
ENABLE_WORKSPACE=$(jq -r '.enable_workspace // true' "$OPTIONS_FILE")
WORKSPACE_PORT=$(jq -r '.workspace_port // 3000' "$OPTIONS_FILE")
GW_PUBLIC_URL=$(jq -r '.gateway_public_url // empty' "$OPTIONS_FILE")
HA_TOKEN=$(jq -r '.homeassistant_token // empty' "$OPTIONS_FILE")
ENABLE_BUILTIN_HA_TOOLS=$(jq -r '.enable_builtin_ha_tools // true' "$OPTIONS_FILE")
ENABLE_HA_SERVICE_CALLS=$(jq -r '.enable_ha_service_calls // false' "$OPTIONS_FILE")
ADDON_HTTP_PROXY=$(jq -r '.http_proxy // empty' "$OPTIONS_FILE")
ENABLE_TERMINAL=$(jq -r '.enable_terminal // true' "$OPTIONS_FILE")
TERMINAL_PORT_RAW="$(jq -r --arg default_port "$DEFAULT_TERMINAL_PORT" '.terminal_port // ($default_port | tonumber)' "$OPTIONS_FILE")"

# SECURITY: Validate TERMINAL_PORT to prevent nginx config injection
# Only allow numeric values in valid port range (1024-65535)
if [[ "$TERMINAL_PORT_RAW" =~ ^[0-9]+$ ]] && [ "$TERMINAL_PORT_RAW" -ge 1024 ] && [ "$TERMINAL_PORT_RAW" -le 65535 ]; then
  TERMINAL_PORT="$TERMINAL_PORT_RAW"
else
  echo "ERROR: Invalid terminal_port '$TERMINAL_PORT_RAW'. Must be numeric 1024-65535. Using default ${DEFAULT_TERMINAL_PORT}."
  TERMINAL_PORT="$DEFAULT_TERMINAL_PORT"
fi

echo "DEBUG: enable_terminal config value: '$ENABLE_TERMINAL'"
echo "DEBUG: terminal_port config value: '$TERMINAL_PORT' (validated)"

# Generic router SSH settings
ROUTER_HOST=$(jq -r '.router_ssh_host // empty' "$OPTIONS_FILE")
ROUTER_USER=$(jq -r '.router_ssh_user // empty' "$OPTIONS_FILE")
ROUTER_KEY=$(jq -r '.router_ssh_key_path // "/data/keys/router_ssh"' "$OPTIONS_FILE")

# Optional: allow disabling lock cleanup if you ever need to debug
CLEAN_LOCKS_ON_START=$(jq -r '.clean_session_locks_on_start // true' "$OPTIONS_FILE")
CLEAN_LOCKS_ON_EXIT=$(jq -r '.clean_session_locks_on_exit // true' "$OPTIONS_FILE")

# Gateway configuration
GATEWAY_MODE=$(jq -r '.gateway_mode // "local"' "$OPTIONS_FILE")
GATEWAY_REMOTE_URL=$(jq -r '.gateway_remote_url // empty' "$OPTIONS_FILE")
GATEWAY_BIND_MODE=$(jq -r '.gateway_bind_mode // "loopback"' "$OPTIONS_FILE")
GATEWAY_PORT="$(jq -r --arg default_port "$DEFAULT_GATEWAY_PORT" '.gateway_port // ($default_port | tonumber)' "$OPTIONS_FILE")"
ENABLE_OPENAI_API=$(jq -r '.enable_openai_api // false' "$OPTIONS_FILE")
GATEWAY_AUTH_MODE=$(jq -r '.gateway_auth_mode // "token"' "$OPTIONS_FILE")
GATEWAY_TRUSTED_PROXIES=$(jq -r '.gateway_trusted_proxies // empty' "$OPTIONS_FILE")
GATEWAY_ADDITIONAL_ALLOWED_ORIGINS=$(jq -r '.gateway_additional_allowed_origins // empty' "$OPTIONS_FILE")
CONTROLUI_DISABLE_DEVICE_AUTH=$(jq -r '.controlui_disable_device_auth // true' "$OPTIONS_FILE")
DISABLE_EXEC_APPROVALS=$(jq -r '.disable_exec_approvals // true' "$OPTIONS_FILE")
FORCE_IPV4_DNS=$(jq -r '.force_ipv4_dns // true' "$OPTIONS_FILE")
ACCESS_MODE=$(jq -r '.access_mode // "custom"' "$OPTIONS_FILE")
NGINX_LOG_LEVEL=$(jq -r '.nginx_log_level // "minimal"' "$OPTIONS_FILE")
AUTO_CONFIGURE_MCP=$(jq -r '.auto_configure_mcp // false' "$OPTIONS_FILE")
ENABLE_CONTEXT7=$(jq -r '.enable_context7 // false' "$OPTIONS_FILE")
CONTEXT7_API_KEY=$(jq -r '.context7_api_key // empty' "$OPTIONS_FILE")
DOMOTZ_API_KEY=$(jq -r '.domotz_api_key // empty' "$OPTIONS_FILE")
DOMOTZ_SITE_ID=$(jq -r '.domotz_site_id // empty' "$OPTIONS_FILE")
GITHUB_ISSUES_TOKEN=$(jq -r '.github_issues_token // empty' "$OPTIONS_FILE")
ENABLE_MATRIX=$(jq -r '.enable_matrix // false' "$OPTIONS_FILE")
MATRIX_HOMESERVER=$(jq -r '.matrix_homeserver // empty' "$OPTIONS_FILE")
MATRIX_ALLOW_PRIVATE_NETWORK=$(jq -r '.matrix_allow_private_network // false' "$OPTIONS_FILE")
MATRIX_USER_ID=$(jq -r '.matrix_user_id // empty' "$OPTIONS_FILE")
MATRIX_ACCESS_TOKEN=$(jq -r '.matrix_access_token // empty' "$OPTIONS_FILE")
MATRIX_PASSWORD=$(jq -r '.matrix_password // empty' "$OPTIONS_FILE")
MATRIX_ENCRYPTION=$(jq -r '.matrix_encryption // false' "$OPTIONS_FILE")
MATRIX_DM_POLICY=$(jq -r '.matrix_dm_policy // "pairing"' "$OPTIONS_FILE")
MATRIX_DM_ALLOW_FROM=$(jq -r '.matrix_dm_allow_from // empty' "$OPTIONS_FILE")
MATRIX_GROUP_POLICY=$(jq -r '.matrix_group_policy // "open"' "$OPTIONS_FILE")
MATRIX_GROUP_ALLOW_FROM=$(jq -r '.matrix_group_allow_from // empty' "$OPTIONS_FILE")
MATRIX_ROOM_ALLOWLIST=$(jq -r '.matrix_room_allowlist // empty' "$OPTIONS_FILE")
MATRIX_AUTO_JOIN=$(jq -r '.matrix_auto_join // "always"' "$OPTIONS_FILE")
MATRIX_STARTUP_STATE="$(matrix_startup_precheck "$ENABLE_MATRIX" "$MATRIX_HOMESERVER" "$MATRIX_USER_ID" "$MATRIX_PASSWORD" "$MATRIX_ACCESS_TOKEN")"
MATRIX_EFFECTIVE_ENABLED="false"
if [ "$MATRIX_STARTUP_STATE" = "ready" ]; then
  MATRIX_EFFECTIVE_ENABLED="true"
elif [ "$MATRIX_STARTUP_STATE" = "missing-homeserver" ]; then
  echo "WARN: Matrix requested but matrix_homeserver is empty; skipping Matrix plugin install and leaving the Matrix channel disabled."
elif [ "$MATRIX_STARTUP_STATE" = "missing-auth" ]; then
  echo "WARN: Matrix requested but no usable auth is configured; skipping Matrix plugin install and leaving the Matrix channel disabled."
fi
MQTT_BROKER_URL=$(jq -r '.mqtt_broker_url // empty' "$OPTIONS_FILE")
MQTT_USERNAME=$(jq -r '.mqtt_username // empty' "$OPTIONS_FILE")
MQTT_PASSWORD=$(jq -r '.mqtt_password // empty' "$OPTIONS_FILE")
ENABLE_BACNET_SCOUT=$(jq -r '.enable_bacnet_scout // false' "$OPTIONS_FILE")
GW_ENV_VARS_TYPE=$(jq -r 'if .gateway_env_vars == null then "null" else (.gateway_env_vars | type) end' "$OPTIONS_FILE")
GW_ENV_VARS_RAW=$(jq -r '.gateway_env_vars // empty' "$OPTIONS_FILE")
GW_ENV_VARS_JSON=$(jq -c '.gateway_env_vars // []' "$OPTIONS_FILE")

export TZ="$TZNAME"
export HOME_ASSISTANT_CONFIG_DIR

if [ -d "$HOME_ASSISTANT_CONFIG_DIR" ]; then
  if [ -f "$HOME_ASSISTANT_CONFIG_DIR/configuration.yaml" ]; then
    echo "INFO: Home Assistant config root mounted at ${HOME_ASSISTANT_CONFIG_DIR}."
  else
    echo "WARN: ${HOME_ASSISTANT_CONFIG_DIR} is mounted but configuration.yaml is missing."
  fi
else
  echo "WARN: Home Assistant config root is not mounted at ${HOME_ASSISTANT_CONFIG_DIR}; in-place HA diagnosis will be limited."
fi

# ------------------------------------------------------------------------------
# Access mode presets — override individual gateway settings for common scenarios
# ------------------------------------------------------------------------------
ENABLE_HTTPS_PROXY=false
GATEWAY_INTERNAL_PORT="$GATEWAY_PORT"

case "$ACCESS_MODE" in
  local_only)
    GATEWAY_BIND_MODE="loopback"
    GATEWAY_AUTH_MODE="token"
    echo "INFO: Access mode: local_only (loopback + token, Ingress/terminal only)"
    ;;
  lan_https)
    # Gateway binds loopback on internal port; nginx terminates TLS on the external port.
    GATEWAY_BIND_MODE="loopback"
    GATEWAY_AUTH_MODE="token"
    ENABLE_HTTPS_PROXY=true
    GATEWAY_INTERNAL_PORT=$((GATEWAY_PORT + 1))
    echo "INFO: Access mode: lan_https (built-in HTTPS proxy on 0.0.0.0:${GATEWAY_PORT})"
    ;;
  lan_reverse_proxy)
    GATEWAY_BIND_MODE="lan"
    GATEWAY_AUTH_MODE="trusted-proxy"
    if [ -z "$GATEWAY_TRUSTED_PROXIES" ]; then
      echo "ERROR: access_mode=lan_reverse_proxy requires gateway_trusted_proxies to be set."
      echo "ERROR: Set it to your reverse proxy's IP/CIDR (e.g. 127.0.0.1,192.168.88.0/24)."
    fi
    echo "INFO: Access mode: lan_reverse_proxy (LAN bind + trusted-proxy auth)"
    ;;
  tailnet_https)
    GATEWAY_BIND_MODE="tailnet"
    GATEWAY_AUTH_MODE="token"
    echo "INFO: Access mode: tailnet_https (Tailscale bind + token auth)"
    ;;
  custom|*)
    echo "INFO: Access mode: custom (using individual gateway_bind_mode/auth_mode settings)"
    ;;
esac

# Reduce risk of secrets ending up in logs
set +x

# Optional outbound proxy from add-on settings.
# If set, apply it to both HTTP and HTTPS for Node/undici/Hermes tooling.
if [ -n "$ADDON_HTTP_PROXY" ]; then
  if [[ "$ADDON_HTTP_PROXY" =~ ^https?://[^[:space:]]+$ ]]; then
    # Keep local traffic direct to avoid accidental proxying of loopback/LAN services.
    DEFAULT_NO_PROXY="localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,.local"

    export HTTP_PROXY="$ADDON_HTTP_PROXY"
    export HTTPS_PROXY="$ADDON_HTTP_PROXY"
    export http_proxy="$ADDON_HTTP_PROXY"
    export https_proxy="$ADDON_HTTP_PROXY"
    export NO_PROXY="${NO_PROXY:+${NO_PROXY},}${DEFAULT_NO_PROXY}"
    export no_proxy="${no_proxy:+${no_proxy},}${DEFAULT_NO_PROXY}"
    echo "INFO: Outbound HTTP/HTTPS proxy enabled from add-on configuration."
    echo "INFO: Applied NO_PROXY defaults for localhost/private network ranges."
  else
    echo "WARN: Invalid http_proxy value in add-on options; expected URL like http://host:port"
  fi
fi

# Optional network hardening/workaround: force IPv4-first DNS ordering for Node.js.
# Helps in environments where IPv6 resolves but has no working egress.
if [ "$FORCE_IPV4_DNS" = "true" ] || [ "$FORCE_IPV4_DNS" = "1" ]; then
  if [ -n "${NODE_OPTIONS:-}" ]; then
    export NODE_OPTIONS="${NODE_OPTIONS} --dns-result-order=ipv4first"
  else
    export NODE_OPTIONS="--dns-result-order=ipv4first"
  fi
  echo "INFO: Enabled IPv4-first DNS ordering (NODE_OPTIONS=--dns-result-order=ipv4first)"
fi

# Home Assistant maps addon_config to /addon_configs/{REPO}_{SLUG} on the host.
export HOME=/config

# Explicitly set Hermes directories to ensure they persist across add-on updates
# This prevents loss of installed skills, configuration, and workspace state
export HERMES_CONFIG_DIR=/config/.hermes
export HERMES_WORKSPACE_DIR=/config/homeops
export XDG_CONFIG_HOME=/config
export HERMES_SKILLS_DIR=/config/.hermes/skills
export HERMES_SYSTEM_GRAPH_PATH=/config/.hermes/gitdakky-system-graph.sqlite3
export HA_REST_BASE_URL="http://supervisor/core/api"
export HA_WS_URL="ws://supervisor/core/websocket"
export HA_WRITE_TOOLS_ENABLED="$ENABLE_HA_SERVICE_CALLS"

mkdir -p /config/.hermes /config/.hermes/identity /config/homeops /config/keys /config/secrets

seed_managed_workspace_files() {
  if [ ! -d "$BOOTSTRAP_SOURCE_DIR" ]; then
    echo "WARN: Managed workspace bootstrap directory missing at $BOOTSTRAP_SOURCE_DIR"
    return 0
  fi

  mkdir -p "$HERMES_WORKSPACE_DIR"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --ignore-existing "${BOOTSTRAP_SOURCE_DIR}/" "${HERMES_WORKSPACE_DIR}/" 2>/dev/null || true
  else
    find "$BOOTSTRAP_SOURCE_DIR" -maxdepth 1 -type f -name '*.md' -print0 | while IFS= read -r -d '' source_file; do
      target_file="${HERMES_WORKSPACE_DIR}/$(basename "$source_file")"
      [ -f "$target_file" ] || cp "$source_file" "$target_file"
    done
  fi
  echo "INFO: Seeded managed workspace bootstrap files into ${HERMES_WORKSPACE_DIR}"
}

seed_managed_workspace_files

DEFAULT_AGENT_ID="main"
DEFAULT_AGENT_ROOT="/config/.hermes/agents/${DEFAULT_AGENT_ID}"
DEFAULT_AGENT_STATE_DIR="${DEFAULT_AGENT_ROOT}/agent"
DEFAULT_AGENT_SESSIONS_DIR="${DEFAULT_AGENT_ROOT}/sessions"
LEGACY_AGENT_STATE_DIR="/config/.hermes/agent"
LEGACY_SESSIONS_DIR="/config/.hermes/sessions"
LEGACY_STATE_MIGRATION_MARKER="/config/.hermes/.gitdakky-agent-layout-migration"

ensure_default_agent_layout() {
  mkdir -p "$DEFAULT_AGENT_STATE_DIR" "$DEFAULT_AGENT_SESSIONS_DIR"
  chmod 700 "$DEFAULT_AGENT_ROOT" "$DEFAULT_AGENT_STATE_DIR" "$DEFAULT_AGENT_SESSIONS_DIR" 2>/dev/null || true
}

run_safe_doctor_state_migration() {
  local log_file="/tmp/hermes-doctor-migration.log"

  if ! legacy_agent_state_needs_migration "$LEGACY_AGENT_STATE_DIR" "$LEGACY_SESSIONS_DIR" "$DEFAULT_AGENT_STATE_DIR" "$DEFAULT_AGENT_SESSIONS_DIR"; then
    return 0
  fi

  echo "INFO: Running safe Hermes doctor migration for legacy agent/session layout..."
  if hermes doctor --non-interactive >"$log_file" 2>&1; then
    echo "INFO: Hermes doctor completed safe migrations."
  else
    echo "WARN: hermes doctor --non-interactive did not complete cleanly; falling back to direct state sync."
    tail -n 20 "$log_file" 2>/dev/null || true
  fi
}

fallback_sync_default_agent_state() {
  local migrated_any=false

  ensure_default_agent_layout

  if [ -d "$LEGACY_AGENT_STATE_DIR" ]; then
    echo "INFO: Syncing legacy agent state into ${DEFAULT_AGENT_STATE_DIR} ..."
    rsync -a --ignore-existing "${LEGACY_AGENT_STATE_DIR}/" "${DEFAULT_AGENT_STATE_DIR}/"
    migrated_any=true
  fi

  if [ -d "$LEGACY_SESSIONS_DIR" ]; then
    echo "INFO: Syncing legacy sessions into ${DEFAULT_AGENT_SESSIONS_DIR} ..."
    rsync -a --ignore-existing "${LEGACY_SESSIONS_DIR}/" "${DEFAULT_AGENT_SESSIONS_DIR}/"
    migrated_any=true
  fi

  if [ -f "$DEFAULT_AGENT_STATE_DIR/auth-profiles.json" ]; then
    chmod 600 "$DEFAULT_AGENT_STATE_DIR/auth-profiles.json" 2>/dev/null || true
  fi

  if [ "$migrated_any" = true ]; then
    {
      echo "migrated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "source_agent_dir=${LEGACY_AGENT_STATE_DIR}"
      echo "source_sessions_dir=${LEGACY_SESSIONS_DIR}"
    } > "$LEGACY_STATE_MIGRATION_MARKER"
  fi
}

reconcile_default_agent_state() {
  ensure_default_agent_layout

  if ! legacy_agent_state_needs_migration "$LEGACY_AGENT_STATE_DIR" "$LEGACY_SESSIONS_DIR" "$DEFAULT_AGENT_STATE_DIR" "$DEFAULT_AGENT_SESSIONS_DIR"; then
    return 0
  fi

  run_safe_doctor_state_migration

  if legacy_agent_state_needs_migration "$LEGACY_AGENT_STATE_DIR" "$LEGACY_SESSIONS_DIR" "$DEFAULT_AGENT_STATE_DIR" "$DEFAULT_AGENT_SESSIONS_DIR"; then
    echo "INFO: Legacy state still present after doctor; copying missing files into agents/${DEFAULT_AGENT_ID}/..."
    fallback_sync_default_agent_state
  fi
}

# ------------------------------------------------------------------------------
# Sync built-in Hermes skills from image to persistent storage
# On each startup, copy new/updated built-in skills so they survive rebuilds.
# We sync them to /config/.hermes/skills and symlink back.
# NOTE: We cannot use `npm root -g` here because HOME=/config may contain a
# persisted .npmrc with a custom prefix from a previous run. Instead, we
# resolve the real image path by temporarily overriding HOME.
# ------------------------------------------------------------------------------
IMAGE_SKILLS_DIR="$(HOME=/root npm root -g 2>/dev/null)/hermes/skills"
PERSISTENT_SKILLS_DIR="/config/.hermes/skills"

if [ -d "$IMAGE_SKILLS_DIR" ] && [ ! -L "$IMAGE_SKILLS_DIR" ]; then
  mkdir -p "$PERSISTENT_SKILLS_DIR"
  # Sync skills: --update replaces older files so upgrades propagate,
  # but doesn't delete user-added files in persistent storage.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --update "$IMAGE_SKILLS_DIR/" "$PERSISTENT_SKILLS_DIR/" 2>/dev/null || true
  else
    cp -ru "$IMAGE_SKILLS_DIR/"* "$PERSISTENT_SKILLS_DIR/" 2>/dev/null || true
  fi
  # Replace image skills dir with symlink to persistent copy
  rm -rf "$IMAGE_SKILLS_DIR"
  ln -sf "$PERSISTENT_SKILLS_DIR" "$IMAGE_SKILLS_DIR"
  echo "INFO: Synced built-in skills to persistent storage at $PERSISTENT_SKILLS_DIR"
elif [ -L "$IMAGE_SKILLS_DIR" ]; then
  echo "INFO: Built-in skills already linked to persistent storage"
else
  echo "WARN: Built-in skills directory not found at $IMAGE_SKILLS_DIR"
fi

seed_bundled_skill_pack() {
  if [ ! -d "$BUNDLED_SKILLS_SOURCE_DIR" ]; then
    echo "WARN: Managed bundled skills directory missing at $BUNDLED_SKILLS_SOURCE_DIR"
    return 0
  fi

  mkdir -p "$PERSISTENT_SKILLS_DIR"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --ignore-existing "${BUNDLED_SKILLS_SOURCE_DIR}/" "${PERSISTENT_SKILLS_DIR}/" 2>/dev/null || true
  else
    find "$BUNDLED_SKILLS_SOURCE_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' source_dir; do
      target_dir="${PERSISTENT_SKILLS_DIR}/$(basename "$source_dir")"
      [ -d "$target_dir" ] || cp -R "$source_dir" "$target_dir"
    done
  fi
  echo "INFO: Seeded GitDakky bundled skills into ${PERSISTENT_SKILLS_DIR}"
}

seed_bundled_skill_pack

# ------------------------------------------------------------------------------
# Persist user-installed node skills across Docker image rebuilds
# Redirect npm/pnpm global installs to /config/.node_global (persistent storage)
# so that skills installed via the dashboard survive container rebuilds.
# NOTE: This MUST come after the skills sync above (which needs the original npm root -g).
# ------------------------------------------------------------------------------
PERSISTENT_NODE_GLOBAL="/config/.node_global"
mkdir -p "$PERSISTENT_NODE_GLOBAL"
npm config set prefix "$PERSISTENT_NODE_GLOBAL" 2>/dev/null || true
export PATH="${PERSISTENT_NODE_GLOBAL}/bin:${PATH}"
export NODE_PATH="${PERSISTENT_NODE_GLOBAL}/lib/node_modules:${NODE_PATH:-}"

# Also configure pnpm global dir to persistent storage
export PNPM_HOME="${PERSISTENT_NODE_GLOBAL}/pnpm"
mkdir -p "$PNPM_HOME"
export PATH="${PNPM_HOME}:${PATH}"

# Protect critical runtime variables from accidental override via gateway_env_vars.
is_reserved_gateway_env_var() {
  case "$1" in
    # Critical runtime paths/process vars.
    HOME|PATH|PWD|OLDPWD|SHLVL|TZ|XDG_CONFIG_HOME|PNPM_HOME|NODE_PATH|NODE_OPTIONS|NODE_NO_WARNINGS)
      return 0
      ;;
    # Low-level injection vectors that can alter process/linker/shell behavior.
    LD_*|DYLD_*|BASH_ENV|ENV|BASH_FUNC_*)
      return 0
      ;;
    # Proxy vars managed by add-on options.
    HTTP_PROXY|HTTPS_PROXY|NO_PROXY|http_proxy|https_proxy|no_proxy)
      return 0
      ;;
    # Add-on internal control vars.
    HERMES_*|HA_REST_BASE_URL|HA_WS_URL|HA_WRITE_TOOLS_ENABLED|SUPERVISOR_TOKEN)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

try_export_gateway_env_var() {
  local key="$1"
  local value="$2"

  if [ -z "$key" ]; then
    return 0
  fi

  # Validate variable name format
  if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "WARN: Invalid environment variable name: '$key' (must start with letter/underscore, skip)"
    return 0
  fi

  # Protect critical runtime variables from accidental override.
  if is_reserved_gateway_env_var "$key"; then
    echo "WARN: Reserved environment variable '$key' cannot be overridden via gateway_env_vars (skip)"
    return 0
  fi

  # Enforce max variable name length
  if [ ${#key} -gt $max_var_name_size ]; then
    echo "WARN: Environment variable name too long: '$key' (max $max_var_name_size chars, skip)"
    return 0
  fi

  # Enforce max variable value length
  if [ ${#value} -gt $max_var_value_size ]; then
    echo "WARN: Environment variable value too long for '$key' (max $max_var_value_size chars, skip)"
    return 0
  fi

  # Enforce limit on number of variables
  if [ $env_count -ge $max_env_vars ]; then
    echo "WARN: Maximum environment variables limit ($max_env_vars) reached (skip)"
    return 0
  fi

  export "$key=$value"
  env_count=$((env_count + 1))
  echo "INFO: Exported gateway env var: $key"
}

# Export gateway environment variables from add-on config
# These are user-defined variables that should be available to the gateway process.
# Primary format: array of {name, value} objects.
if [ "$GW_ENV_VARS_TYPE" = "array" ] || [ "$GW_ENV_VARS_TYPE" = "object" ] || { [ "$GW_ENV_VARS_TYPE" = "string" ] && [ -n "$GW_ENV_VARS_RAW" ]; }; then
  env_count=0
  max_env_vars=50
  max_var_name_size=255
  max_var_value_size=10000

  if [ "$GW_ENV_VARS_TYPE" = "array" ] && [ "$GW_ENV_VARS_JSON" != "[]" ]; then
    echo "INFO: Setting gateway environment variables from list config..."

    invalid_entries_count=$(printf '%s' "$GW_ENV_VARS_JSON" | jq '[.[] | select((type != "object") or ((.name | type) != "string") or (has("value") | not))] | length')
    if [ "$invalid_entries_count" -gt 0 ]; then
      echo "WARN: Found $invalid_entries_count invalid gateway_env_vars entries; expected objects with 'name' and 'value' keys (skip)"
    fi

    while IFS= read -r -d '' key && IFS= read -r -d '' value; do
      try_export_gateway_env_var "$key" "$value"
    done < <(printf '%s' "$GW_ENV_VARS_JSON" | jq -j '.[] | select((type == "object") and ((.name | type) == "string") and (has("value"))) | .name, "\u0000", (.value | tostring), "\u0000"')
  elif [ "$GW_ENV_VARS_TYPE" = "object" ] && [ "$GW_ENV_VARS_JSON" != "{}" ]; then
    # Backward compatibility for old map/object configuration.
    echo "INFO: Setting gateway environment variables from object config (legacy format)..."
    while IFS= read -r -d '' key && IFS= read -r -d '' value; do
      try_export_gateway_env_var "$key" "$value"
    done < <(printf '%s' "$GW_ENV_VARS_JSON" | jq -j 'to_entries[] | .key, "\u0000", (.value | tostring), "\u0000"')
  elif [ "$GW_ENV_VARS_TYPE" = "string" ] && [ -n "$GW_ENV_VARS_RAW" ]; then
    # Preferred for complex values: JSON object string in one line.
    if printf '%s' "$GW_ENV_VARS_RAW" | jq -e 'type == "object"' >/dev/null 2>&1; then
      echo "INFO: Setting gateway environment variables from JSON string config..."
      while IFS= read -r -d '' key && IFS= read -r -d '' value; do
        try_export_gateway_env_var "$key" "$value"
      done < <(printf '%s' "$GW_ENV_VARS_RAW" | jq -j 'to_entries[] | .key, "\u0000", (.value | tostring), "\u0000"')
    else
      # Supported simple format: KEY=VALUE pairs separated by ';' or newlines.
      echo "INFO: Setting gateway environment variables from KEY=VALUE string config..."
      while IFS= read -r entry; do
        entry="${entry%$'\r'}"
        trimmed="$(printf '%s' "$entry" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"

        # Skip empty lines and comments.
        if [ -z "$trimmed" ] || [[ "$trimmed" == \#* ]]; then
          continue
        fi

        if [[ "$trimmed" != *"="* ]]; then
          echo "WARN: Invalid gateway_env_vars entry '$trimmed' (expected KEY=VALUE, skip)"
          continue
        fi

        key="${trimmed%%=*}"
        value="${trimmed#*=}"
        key="$(printf '%s' "$key" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"

        try_export_gateway_env_var "$key" "$value"
      done < <(printf '%s' "$GW_ENV_VARS_RAW" | tr ';' '\n')
    fi
  fi

  if [ $env_count -gt 0 ]; then
    echo "INFO: Successfully exported $env_count gateway environment variable(s)"
  fi
elif [ "$GW_ENV_VARS_TYPE" != "null" ]; then
  echo "WARN: Invalid gateway_env_vars format in add-on options (expected list, string or object), skipping"
fi

# ------------------------------------------------------------------------------
# Persist Linuxbrew/Homebrew across Docker image rebuilds
# Homebrew installs to /home/linuxbrew/.linuxbrew/ which is ephemeral.
# We sync it to /config/.linuxbrew and symlink back so brew-installed CLI
# tools (gog, gh, bw, etc.) survive add-on updates.
# ------------------------------------------------------------------------------
IMAGE_BREW_DIR="/home/linuxbrew/.linuxbrew"
PERSISTENT_BREW_DIR="/config/.linuxbrew"

if [ -d "$IMAGE_BREW_DIR" ] && [ ! -L "$IMAGE_BREW_DIR" ]; then
  # Image has a real Homebrew install — sync to persistent storage
  if [ -d "$PERSISTENT_BREW_DIR" ]; then
    # Persistent copy exists: sync new/updated files from image (upgrades),
    # but preserve user-installed packages already in persistent storage.
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --update "$IMAGE_BREW_DIR/" "$PERSISTENT_BREW_DIR/" 2>/dev/null || true
    else
      cp -ru "$IMAGE_BREW_DIR/"* "$PERSISTENT_BREW_DIR/" 2>/dev/null || true
    fi
    echo "INFO: Synced Homebrew updates to persistent storage"
  else
    # First time: copy entire Homebrew install to persistent storage
    cp -a "$IMAGE_BREW_DIR" "$PERSISTENT_BREW_DIR" 2>/dev/null || true
    echo "INFO: Copied Homebrew to persistent storage at $PERSISTENT_BREW_DIR"
  fi
  # Replace image dir with symlink to persistent copy
  rm -rf "$IMAGE_BREW_DIR"
  ln -sf "$PERSISTENT_BREW_DIR" "$IMAGE_BREW_DIR"
elif [ -L "$IMAGE_BREW_DIR" ]; then
  echo "INFO: Homebrew already linked to persistent storage"
elif [ -d "$PERSISTENT_BREW_DIR" ]; then
  # Image doesn't have Homebrew (failed install?) but persistent copy exists
  mkdir -p "$(dirname "$IMAGE_BREW_DIR")"
  ln -sf "$PERSISTENT_BREW_DIR" "$IMAGE_BREW_DIR"
  echo "INFO: Restored Homebrew symlink from persistent storage"
else
  echo "INFO: Homebrew not available (install may have failed during image build)"
fi

# Back-compat: some docs/scripts assume /data; point it at /config.
if [ ! -e /data ]; then
  ln -s /config /data || true
fi

# Ensure the agents base directory exists so cleanup scans work even before first run.
# Do NOT pre-create agent-specific directories; Hermes creates them as needed.
mkdir -p /config/.hermes/agents || true

# ------------------------------------------------------------------------------
# SINGLE-INSTANCE GUARD (prevents multiple gateway runs racing each other)
# ------------------------------------------------------------------------------
STARTUP_LOCK="/config/.hermes/gateway.start.lock"
exec 9>"$STARTUP_LOCK"
if ! flock -n 9; then
  echo "ERROR: Another instance appears to be running (could not acquire $STARTUP_LOCK)."
  echo "If this is wrong, check for stuck processes or remove the lock file."
  exit 1
fi

# ------------------------------------------------------------------------------
# Session lock cleanup helpers
# ------------------------------------------------------------------------------

gateway_running() {
  pgrep -f "hermes-gateway" >/dev/null 2>&1
}

cleanup_session_locks() {
  local agents_dir="/config/.hermes/agents"
  local total_locks=0
  local cleaned_dirs=()

  # Scan all agent session directories, not just 'main'.
  # This is needed for users who have gateway.forcedAgentId set to a non-default agent.
  shopt -s nullglob
  local all_locks=()
  for agent_sessions_dir in "${agents_dir}"/*/sessions; do
    local agent_locks=( "${agent_sessions_dir}"/*.jsonl.lock )
    if [ ${#agent_locks[@]} -gt 0 ]; then
      all_locks+=( "${agent_locks[@]}" )
      cleaned_dirs+=( "$agent_sessions_dir" )
      total_locks=$(( total_locks + ${#agent_locks[@]} ))
    fi
  done
  shopt -u nullglob

  if [ "$total_locks" -eq 0 ]; then
    return 0
  fi

  # If gateway is running, do NOT remove locks automatically (could be real).
  if gateway_running; then
    echo "INFO: Gateway appears to be running; leaving session lock files untouched."
    echo "INFO: Locks present: $total_locks"
    return 0
  fi

  echo "INFO: Removing stale session lock files ($total_locks) across agents: ${cleaned_dirs[*]}"
  for agent_sessions_dir in "${cleaned_dirs[@]}"; do
    rm -f "${agent_sessions_dir}"/*.jsonl.lock || true
  done
}

if [ "$CLEAN_LOCKS_ON_START" = "true" ]; then
  cleanup_session_locks
else
  echo "INFO: clean_session_locks_on_start=false; skipping session lock cleanup."
fi

# ------------------------------------------------------------------------------
# Store tokens / export env vars (optional)
# ------------------------------------------------------------------------------

if [ -n "$HA_TOKEN" ]; then
  umask 077
  printf '%s' "$HA_TOKEN" > /config/secrets/homeassistant.token
fi

write_secret_file() {
  local target_path="$1"
  local secret_value="$2"

  mkdir -p "$(dirname "$target_path")"
  if [ -n "$secret_value" ]; then
    umask 077
    printf '%s' "$secret_value" > "$target_path"
  else
    rm -f "$target_path"
  fi
}

configure_external_integrations() {
  write_secret_file /config/secrets/context7.api_key "$CONTEXT7_API_KEY"
  write_secret_file /config/secrets/domotz.api_key "$DOMOTZ_API_KEY"
  write_secret_file /config/secrets/domotz.site_id "$DOMOTZ_SITE_ID"
  write_secret_file /config/secrets/github_issues.token "$GITHUB_ISSUES_TOKEN"
  write_secret_file /config/secrets/matrix.access_token "$MATRIX_ACCESS_TOKEN"
  write_secret_file /config/secrets/matrix.password "$MATRIX_PASSWORD"
  write_secret_file /config/secrets/mqtt.broker_url "$MQTT_BROKER_URL"
  write_secret_file /config/secrets/mqtt.username "$MQTT_USERNAME"
  write_secret_file /config/secrets/mqtt.password "$MQTT_PASSWORD"

  export CONTEXT7_ENABLED=false
  export DOMOTZ_ENABLED=false
  export MQTT_ENABLED=false
  export BACNET_SCOUT_ENABLED=false
  export MATRIX_ENABLED=false
  export MATRIX_ACCESS_TOKEN_CONFIGURED=false
  export MATRIX_PASSWORD_CONFIGURED=false
  export MQTT_USERNAME_CONFIGURED=false
  export MQTT_PASSWORD_CONFIGURED=false
  export HA_MCP_ENABLED=false
  export GITHUB_ISSUES_ENABLED=false
  export GITDAKKY_ISSUES_REPO="GitDakky/homeops-ai"

  if [ "$ENABLE_CONTEXT7" = "true" ] || [ "$ENABLE_CONTEXT7" = "1" ]; then
    export CONTEXT7_ENABLED=true
  fi
  if [ -n "$CONTEXT7_API_KEY" ]; then
    export CONTEXT7_API_KEY
    export CONTEXT7_API_KEY_FILE=/config/secrets/context7.api_key
  fi

  if [ -n "$DOMOTZ_API_KEY" ] || [ -n "$DOMOTZ_SITE_ID" ]; then
    export DOMOTZ_ENABLED=true
  fi
  if [ -n "$DOMOTZ_API_KEY" ]; then
    export DOMOTZ_API_KEY
    export DOMOTZ_API_KEY_FILE=/config/secrets/domotz.api_key
  fi
  if [ -n "$DOMOTZ_SITE_ID" ]; then
    export DOMOTZ_SITE_ID
    export DOMOTZ_SITE_ID_FILE=/config/secrets/domotz.site_id
  fi

  if [ -n "$GITHUB_ISSUES_TOKEN" ]; then
    export GITHUB_ISSUES_ENABLED=true
    export GITHUB_ISSUES_TOKEN_FILE=/config/secrets/github_issues.token
  fi

  if [ "$MATRIX_EFFECTIVE_ENABLED" = "true" ]; then
    export MATRIX_ENABLED=true
  fi
  export MATRIX_HOMESERVER
  export MATRIX_USER_ID
  export MATRIX_DM_POLICY
  export MATRIX_GROUP_POLICY
  export MATRIX_AUTO_JOIN
  if [ -n "$MATRIX_ACCESS_TOKEN" ]; then
    export MATRIX_ACCESS_TOKEN_FILE=/config/secrets/matrix.access_token
    export MATRIX_ACCESS_TOKEN_CONFIGURED=true
  fi
  if [ -n "$MATRIX_PASSWORD" ]; then
    export MATRIX_PASSWORD_FILE=/config/secrets/matrix.password
    export MATRIX_PASSWORD_CONFIGURED=true
  fi

  if [ -n "$MQTT_BROKER_URL" ]; then
    export MQTT_ENABLED=true
    export MQTT_BROKER_URL
    export MQTT_BROKER_URL_FILE=/config/secrets/mqtt.broker_url
  fi
  if [ -n "$MQTT_USERNAME" ]; then
    export MQTT_USERNAME
    export MQTT_USERNAME_FILE=/config/secrets/mqtt.username
    export MQTT_USERNAME_CONFIGURED=true
  fi
  if [ -n "$MQTT_PASSWORD" ]; then
    export MQTT_PASSWORD
    export MQTT_PASSWORD_FILE=/config/secrets/mqtt.password
    export MQTT_PASSWORD_CONFIGURED=true
  fi

  if [ "$ENABLE_BACNET_SCOUT" = "true" ] || [ "$ENABLE_BACNET_SCOUT" = "1" ]; then
    export BACNET_SCOUT_ENABLED=true
  fi

  if [ "$AUTO_CONFIGURE_MCP" = "true" ] && [ -n "$HA_TOKEN" ]; then
    export HA_MCP_ENABLED=true
  fi

  cat > /config/.hermes/gitdakky-integrations.json <<EOF
{
  "context7": {
    "enabled": ${CONTEXT7_ENABLED},
    "apiKeyConfigured": $( [ -n "$CONTEXT7_API_KEY" ] && echo true || echo false )
  },
  "domotz": {
    "enabled": ${DOMOTZ_ENABLED},
    "siteId": $(printf '%s' "$DOMOTZ_SITE_ID" | jq -Rs .),
    "apiKeyConfigured": $( [ -n "$DOMOTZ_API_KEY" ] && echo true || echo false )
  },
  "githubIssues": {
    "enabled": ${GITHUB_ISSUES_ENABLED},
    "repo": "GitDakky/homeops-ai"
  },
  "matrix": {
    "enabled": ${MATRIX_ENABLED},
    "homeserver": $(printf '%s' "$MATRIX_HOMESERVER" | jq -Rs .),
    "userId": $(printf '%s' "$MATRIX_USER_ID" | jq -Rs .),
    "accessTokenConfigured": ${MATRIX_ACCESS_TOKEN_CONFIGURED},
    "passwordConfigured": ${MATRIX_PASSWORD_CONFIGURED},
    "dmPolicy": $(printf '%s' "$MATRIX_DM_POLICY" | jq -Rs .),
    "groupPolicy": $(printf '%s' "$MATRIX_GROUP_POLICY" | jq -Rs .),
    "autoJoin": $(printf '%s' "$MATRIX_AUTO_JOIN" | jq -Rs .)
  },
  "mqtt": {
    "enabled": ${MQTT_ENABLED},
    "brokerUrl": $(printf '%s' "$MQTT_BROKER_URL" | jq -Rs .),
    "usernameConfigured": ${MQTT_USERNAME_CONFIGURED},
    "passwordConfigured": ${MQTT_PASSWORD_CONFIGURED}
  },
  "bacnet": {
    "enabled": ${BACNET_SCOUT_ENABLED}
  }
}
EOF

  echo "INFO: Prepared external integration secrets and runtime flags."
}

configure_external_integrations


# ------------------------------------------------------------------------------
# Hermes config is managed by Hermes itself (onboarding / configure).
# This add-on intentionally does NOT create/patch /config/.hermes/config.yaml.
# ------------------------------------------------------------------------------

# Convenience info for later (router SSH access path & HA token file)
cat > /config/CONNECTION_NOTES.txt <<EOF
Home Assistant token (if set): /config/secrets/homeassistant.token
GitHub issues token (if set): /config/secrets/github_issues.token
Matrix access token (if set): /config/secrets/matrix.access_token
Matrix password (if set): /config/secrets/matrix.password
Router SSH (generic):
  host=${ROUTER_HOST}
  user=${ROUTER_USER}
  key=${ROUTER_KEY}
EOF


# ------------------------------------------------------------------------------
# Graceful shutdown handling (PID 1 trap) to reduce stale locks
# ------------------------------------------------------------------------------
GW_PID=""
GW_RELAY_PID=""
NGINX_PID=""
TTYD_PID=""
LOCAL_PAIRING_APPROVER_PID=""
DASHBOARD_API_PID=""
CONFIG_WATCHER_PID=""
SHUTTING_DOWN="false"

shutdown() {
  SHUTTING_DOWN="true"
  echo "Shutdown requested; stopping services..."

  if [ -n "${NGINX_PID}" ] && kill -0 "${NGINX_PID}" >/dev/null 2>&1; then
    kill -TERM "${NGINX_PID}" >/dev/null 2>&1 || true
    wait "${NGINX_PID}" || true
  fi

  if [ -n "${TTYD_PID}" ] && kill -0 "${TTYD_PID}" >/dev/null 2>&1; then
    kill -TERM "${TTYD_PID}" >/dev/null 2>&1 || true
    wait "${TTYD_PID}" || true
  fi

  if [ -n "${LOCAL_PAIRING_APPROVER_PID}" ] && kill -0 "${LOCAL_PAIRING_APPROVER_PID}" >/dev/null 2>&1; then
    kill -TERM "${LOCAL_PAIRING_APPROVER_PID}" >/dev/null 2>&1 || true
    wait "${LOCAL_PAIRING_APPROVER_PID}" 2>/dev/null || true
  fi

  if [ -n "${DASHBOARD_API_PID}" ] && kill -0 "${DASHBOARD_API_PID}" >/dev/null 2>&1; then
    kill -TERM "${DASHBOARD_API_PID}" >/dev/null 2>&1 || true
    wait "${DASHBOARD_API_PID}" 2>/dev/null || true
  fi

  if [ -n "${CONFIG_WATCHER_PID}" ] && kill -0 "${CONFIG_WATCHER_PID}" >/dev/null 2>&1; then
    kill -TERM "${CONFIG_WATCHER_PID}" >/dev/null 2>&1 || true
    wait "${CONFIG_WATCHER_PID}" 2>/dev/null || true
  fi

  if [ -n "${GW_PID}" ] && kill -0 "${GW_PID}" >/dev/null 2>&1; then
    kill -TERM "${GW_PID}" >/dev/null 2>&1 || true
    # wait reaps child PIDs; for non-child (re-tracked) PIDs it fails instantly,
    # so fall back to a timed kill -0 poll to let the gateway finish cleanly.
    if ! wait "${GW_PID}" 2>/dev/null; then
      for _i in 1 2 3 4 5; do
        kill -0 "${GW_PID}" 2>/dev/null || break
        sleep 1
      done
    fi
  fi

  stop_gw_relay

  if [ "$CLEAN_LOCKS_ON_EXIT" = "true" ]; then
    cleanup_session_locks || true
  fi
}

trap shutdown INT TERM

if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: hermes is not installed or not on PATH."
  echo "ERROR: The image should install Hermes during build; reinstall the add-on after the latest build completes."
  GW_PID=""
else
  export HOME=/config
  export HERMES_HOME=/config/.hermes
  export HERMES_ACCEPT_HOOKS=1
  export HASS_URL="${HASS_URL:-http://supervisor/core}"
  mkdir -p "$HERMES_HOME" /config/homeops "$RUNTIME_WRAPPER_LOG_DIR"

  # Provider/model workflow: Home Assistant options -> Hermes config/env.
  # OpenRouter is the default because it is provider-agnostic and matches the
  # public HomeOps AI install path. Advanced users can still use gateway_env_vars
  # or the integrated terminal to run `hermes model` / `hermes config set ...`.
  if [ -n "$OPENROUTER_API_KEY_OPTION" ]; then
    export OPENROUTER_API_KEY="$OPENROUTER_API_KEY_OPTION"
  fi

  if [ -n "$LLM_PROVIDER" ]; then
    hermes config set model.provider "$LLM_PROVIDER" >/dev/null 2>&1 || true
  fi
  if [ -n "$LLM_MODEL" ]; then
    hermes config set model.default "$LLM_MODEL" >/dev/null 2>&1 || true
  fi

  # Enable the native Hermes Home Assistant tool path where possible.
  if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    export HASS_TOKEN="$SUPERVISOR_TOKEN"
  fi

  start_hermes_runtime() {
    echo "Starting ${SELF_ADDON_NAME} runtime (Hermes gateway)..."
    mkdir -p "$RUNTIME_WRAPPER_LOG_DIR"
    (
      cd /config/homeops
      exec env         HOME=/config         HERMES_HOME=/config/.hermes         HERMES_ACCEPT_HOOKS=1         API_SERVER_ENABLED=true         API_SERVER_HOST=127.0.0.1         API_SERVER_PORT="$GATEWAY_INTERNAL_PORT"         HASS_URL="${HASS_URL:-http://supervisor/core}"         HASS_TOKEN="${HASS_TOKEN:-}"         OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"         hermes gateway run
    ) < /dev/null >>"$RUNTIME_WRAPPER_LOG_FILE" 2>&1 &
    GW_PID=$!
    echo "INFO: Hermes runtime wrapper log: ${RUNTIME_WRAPPER_LOG_FILE}"
    return 0
  }

  start_dashboard_api() {
    local api_port="${DASHBOARD_API_PORT:-$DEFAULT_DASHBOARD_API_PORT}"
    if [ ! -f /dashboard_api.py ]; then
      echo "WARN: dashboard_api.py not found; operator file editor will be unavailable"
      return 0
    fi
    export HERMES_DASHBOARD_API_PORT="$api_port"
    export HERMES_DASHBOARD_API_PORT="$api_port"
    python3 /dashboard_api.py &
    DASHBOARD_API_PID=$!
    sleep 1
    if kill -0 "$DASHBOARD_API_PID" >/dev/null 2>&1; then
      echo "INFO: Dashboard API started on 127.0.0.1:${api_port}"
    else
      echo "WARN: Dashboard API failed to start; file/schedule widgets may be unavailable"
      DASHBOARD_API_PID=""
    fi
  }

  start_workspace_ui() {
    if [ "$ENABLE_WORKSPACE" != "true" ] && [ "$ENABLE_WORKSPACE" != "1" ]; then
      echo "INFO: Hermes Workspace UI disabled."
      return 0
    fi
    if [ ! -d /opt/hermes-workspace ]; then
      echo "WARN: /opt/hermes-workspace missing; Workspace UI unavailable."
      return 0
    fi
    PORT="$WORKSPACE_PORT" HERMES_API_URL="http://127.0.0.1:${GATEWAY_INTERNAL_PORT}" homeops-workspace >>"$RUNTIME_WRAPPER_LOG_DIR/hermes-workspace.log" 2>&1 &
    WORKSPACE_PID=$!
    echo "INFO: Hermes Workspace UI started on 0.0.0.0:${WORKSPACE_PORT} (PID ${WORKSPACE_PID})."
  }

  start_hermes_runtime || true
  start_dashboard_api || true
  start_workspace_ui || true
fi

# Start web terminal (optional)
TTYD_PID_FILE="/var/run/hermes-ttyd.pid"

# Clean up stale ttyd process from previous run using PID file
if [ -f "$TTYD_PID_FILE" ]; then
  OLD_PID=$(cat "$TTYD_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping previous ttyd process (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    # Force kill if still running
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$TTYD_PID_FILE"
fi

if [ "$ENABLE_TERMINAL" = "true" ] || [ "$ENABLE_TERMINAL" = "1" ]; then
  # Check if the terminal port is already in use before starting ttyd
  if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${TERMINAL_PORT} "; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "!!  WARNING: terminal_port ${TERMINAL_PORT} IS ALREADY IN USE  !!"
    echo "!!                                                             !!"
    echo "!!  The web terminal (ttyd) may FAIL to start because port     !!"
    echo "!!  ${TERMINAL_PORT} appears to be in use by another process.  !!"
    echo "!!                                                             !!"
    echo "!!  ACTION REQUIRED: If the terminal does not work, go to      !!"
    echo "!!  Add-on Configuration and change 'terminal_port' to a free  !!"
    echo "!!  port, then restart the add-on.                             !!"
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
  fi
  echo "Starting web terminal (ttyd) on 127.0.0.1:${TERMINAL_PORT} ..."
  ttyd -W -i 127.0.0.1 -p "${TERMINAL_PORT}" -b /terminal bash &
  TTYD_PID=$!
  echo "$TTYD_PID" > "$TTYD_PID_FILE"
  echo "ttyd started with PID $TTYD_PID"
else
  echo "Terminal disabled (enable_terminal=$ENABLE_TERMINAL)"
fi

# Start ingress reverse proxy (nginx). This provides the add-on UI inside HA.
# Token is injected server-side; never put it in the browser URL.
NGINX_PID_FILE="/var/run/hermes-nginx.pid"

# Clean up stale nginx process from previous run (e.g., after crash/unclean restart)
if [ -f "$NGINX_PID_FILE" ]; then
  OLD_NGINX_PID=$(cat "$NGINX_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$OLD_NGINX_PID" ] && kill -0 "$OLD_NGINX_PID" 2>/dev/null; then
    echo "Stopping previous nginx process (PID $OLD_NGINX_PID)..."
    kill "$OLD_NGINX_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_NGINX_PID" 2>/dev/null || true
  fi
  rm -f "$NGINX_PID_FILE"
fi
# Also kill any orphaned nginx workers that might hold the ingress port
if command -v pkill >/dev/null 2>&1; then
  pkill -f "nginx.*-c /etc/nginx/nginx.conf" 2>/dev/null || true
  sleep 1
fi
# Verify the ingress port is actually free before proceeding
if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${DEFAULT_INGRESS_PORT} "; then
  echo "WARN: Port ${DEFAULT_INGRESS_PORT} still in use after cleanup; nginx may fail to start"
fi

# Render nginx config from template.
# The gateway token is NOT managed by the add-on; Hermes will generate/store it.
# Read directly from config file — the CLI redacts secrets since v2026.2.22+.
GW_TOKEN="$(python3 -c "
import json, os
p = os.environ.get('HERMES_CONFIG_PATH', '/config/.hermes/config.yaml')
print(json.load(open(p)).get('gateway',{}).get('auth',{}).get('token',''), end='')
" 2>/dev/null || true)"

# Collect disk usage for landing page status card
DISK_TOTAL="" DISK_USED="" DISK_AVAIL="" DISK_PCT=""
if df -h /config >/dev/null 2>&1; then
  DISK_TOTAL=$(df -h /config | awk 'NR==2{print $2}')
  DISK_USED=$(df -h /config | awk 'NR==2{print $3}')
  DISK_AVAIL=$(df -h /config | awk 'NR==2{print $4}')
  DISK_PCT=$(df -h /config | awk 'NR==2{print $5}')
  echo "INFO: Disk usage: ${DISK_USED}/${DISK_TOTAL} (${DISK_PCT} used, ${DISK_AVAIL} free)"
  # Warn early if disk is getting full
  DISK_PCT_NUM=${DISK_PCT//%/}
  if [ "$DISK_PCT_NUM" -ge 90 ] 2>/dev/null; then
    echo "WARNING: Disk is ${DISK_PCT} full! Add-on updates may fail. Run 'homeops-cleanup' in the terminal."
  elif [ "$DISK_PCT_NUM" -ge 75 ] 2>/dev/null; then
    echo "NOTICE: Disk is ${DISK_PCT} full. Consider running 'homeops-cleanup' in the terminal."
  fi
fi

GW_PUBLIC_URL="$GW_PUBLIC_URL" GW_TOKEN="$GW_TOKEN" TERMINAL_PORT="$TERMINAL_PORT" \
  ENABLE_HTTPS_PROXY="$ENABLE_HTTPS_PROXY" HTTPS_PROXY_PORT="$GATEWAY_PORT" \
  GATEWAY_INTERNAL_PORT="$GATEWAY_INTERNAL_PORT" GATEWAY_PORT="$GATEWAY_PORT" \
  GATEWAY_MODE="$GATEWAY_MODE" GATEWAY_BIND_MODE="$GATEWAY_BIND_MODE" ACCESS_MODE="$ACCESS_MODE" \
  DISK_TOTAL="$DISK_TOTAL" DISK_USED="$DISK_USED" DISK_AVAIL="$DISK_AVAIL" DISK_PCT="$DISK_PCT" \
  HERMES_BUNDLED_VERSION="${HERMES_BUNDLED_VERSION:-unknown}" \
  DASHBOARD_API_PORT="${HERMES_DASHBOARD_API_PORT:-$DEFAULT_DASHBOARD_API_PORT}" \
  NGINX_LOG_LEVEL="$NGINX_LOG_LEVEL" \
  python3 /render_nginx.py

echo "Starting ingress proxy (nginx) on :${DEFAULT_INGRESS_PORT} ..."
nginx -g 'daemon off;' &
NGINX_PID=$!
sleep 1
if kill -0 "$NGINX_PID" 2>/dev/null; then
  echo "$NGINX_PID" > "$NGINX_PID_FILE"
  echo "nginx started with PID $NGINX_PID"
else
  echo "WARN: nginx failed to start (PID $NGINX_PID exited); ingress UI may be unavailable"
fi

# Keep the add-on alive even if the managed Hermes runtime exits.
# Important: we launch the runtime with Hermes gateway does
# not detach into a fresh PID under the add-on supervisor. The wrapper now owns
# one stable child process and simply restarts it if it exits.
while true; do
  GW_EXIT_CODE=0
  if [ -n "${GW_PID:-}" ]; then
    wait "${GW_PID}" 2>/dev/null || GW_EXIT_CODE=$?
  else
    sleep 5
    GW_EXIT_CODE=127
  fi

  if [ "$SHUTTING_DOWN" = "true" ]; then
    break
  fi

  if [ "$GW_EXIT_CODE" -ne 0 ] && [ -f "$RUNTIME_WRAPPER_LOG_FILE" ]; then
    echo "WARN: Managed Hermes runtime log tail after exit:"
    tail -n 40 "$RUNTIME_WRAPPER_LOG_FILE" 2>/dev/null || true
  fi

  if [ -f "$RUNTIME_RESTART_REQUEST_FILE" ]; then
    RESTART_REASON="$(cat "$RUNTIME_RESTART_REQUEST_FILE" 2>/dev/null || echo "managed-request")"
    rm -f "$RUNTIME_RESTART_REQUEST_FILE"
    echo "INFO: Hermes runtime exited for a managed restart (${RESTART_REASON}). Restarting in 1s..."
    sleep 1
  else
    echo "WARN: Hermes runtime exited with code ${GW_EXIT_CODE}. Restarting in 2s..."
    sleep 2
  fi

  # Stop the loopback relay BEFORE restarting the gateway (tailnet mode only).
  # The relay holds 127.0.0.1:GATEWAY_PORT — leaving it up causes the new gateway
  # to detect the port as occupied and exit with code 1, re-entering the loop.
  stop_gw_relay

  if ! start_hermes_runtime; then
    echo "ERROR: Failed to restart Hermes runtime; retrying in 5s..."
    sleep 5
  else
    rm -f "$RUNTIME_RESTART_REQUEST_FILE"
    start_gw_relay
  fi
done
