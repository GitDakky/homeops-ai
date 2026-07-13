ARG BUILD_ARCH=amd64
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-debian:bookworm
ARG BUILD_ARCH
ARG HERMES_VERSION=v2026.7.7.2
ARG HERMES_WORKSPACE_REPO=https://github.com/outsourc-e/hermes-workspace.git
ARG HERMES_WORKSPACE_REF=main
ARG HERMES_PAPERCLIP_ADAPTER_VERSION=0.3.0

# Base image is Debian Bookworm (glibc). This avoids musl-related native module issues
# that occur on Alpine (e.g. clipboard, node-llama-cpp).

# Install base packages (without nodejs/npm - we'll get Node 22 from NodeSource)
# build-essential provides gcc/cc needed by Homebrew for Hermes's brew-managed dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    openssh-client \
    ca-certificates \
    tzdata \
    jq \
    curl \
    tar \
    xz-utils \
    file \
    python3 \
    nginx \
    gnupg \
    build-essential \
    sudo \
    vim \
    nano \
    fd-find \
    ripgrep \
    rsync \
    bat \
    less \
    openssl \
    sqlite3 \
    mosquitto-clients \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS from NodeSource (Debian Bookworm ships Node 18, but current
# Hermes releases require Node 22.16+ and upstream recommends Node 24 or 22.16+)
# Use explicit keyring + apt source instead of setup_22.x pipe script for deterministic builds.
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && chmod 644 /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && NODE_VERSION="$(node -v)" \
    && echo "$NODE_VERSION" \
    && echo "$NODE_VERSION" | grep -E '^v22\.' \
    && rm -f /etc/apt/sources.list.d/nodesource.list /etc/apt/keyrings/nodesource.gpg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install ttyd (web terminal) - not in Debian repos, download binary
# Docker TARGETARCH: amd64, arm64, arm/v7 → ttyd filenames: x86_64, aarch64, armhf
ARG TARGETARCH
RUN ARCH=$(echo ${TARGETARCH:-$(dpkg --print-architecture)} | sed 's|arm64|aarch64|;s|arm/v7|armhf|;s|armv7|armhf|;s|amd64|x86_64|') \
    && echo "Downloading ttyd for arch: ${ARCH}" \
    && curl -fsSL "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.${ARCH}" -o /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

RUN node -v && npm -v

# Install pnpm globally (required by some Hermes skills like clawhub)
RUN npm install -g pnpm && pnpm -v

# Install Chromium for website automation tasks
# Includes necessary dependencies for headless browser operation
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Homebrew (Linuxbrew) for Hermes skill dependencies
# Homebrew is optional - some skills need CLI tools like gemini, aider, etc.
# NOTE: Homebrew requires CPU with SSSE3 support (Intel Core 2 or newer, ~2006+)
# If installation fails (e.g., older CPUs), the add-on will still work but some skills may not install
ENV HOMEBREW_NO_AUTO_UPDATE=1 \
    HOMEBREW_NO_INSTALL_CLEANUP=1 \
    HOMEBREW_NO_ANALYTICS=1

RUN useradd -m -s /bin/bash linuxbrew \
    && mkdir -p /home/linuxbrew/.linuxbrew \
    && chown -R linuxbrew:linuxbrew /home/linuxbrew

USER linuxbrew
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
    (echo "WARNING: Homebrew installation failed (likely unsupported CPU - requires SSSE3). Some skills may not work." && exit 0)
RUN if [ -d /home/linuxbrew/.linuxbrew/Homebrew ]; then \
    cd /home/linuxbrew/.linuxbrew/Homebrew && \
    git config --global --add safe.directory /home/linuxbrew/.linuxbrew/Homebrew && \
    /home/linuxbrew/.linuxbrew/bin/brew update --force || true; \
    fi
USER root

# Add Homebrew to PATH for all users (wrapper comes first to intercept root calls)
# PATH is set even if brew failed - wrapper will handle missing brew gracefully
ENV PATH="/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"

# Copy brew wrapper that allows root to run brew by delegating to linuxbrew user
COPY brew-wrapper.sh /usr/local/bin/brew
RUN chmod +x /usr/local/bin/brew

# Verify brew is available and install gcc (needed for compiling some brew packages)
# Skip if brew installation failed
USER linuxbrew
RUN if [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then \
    /home/linuxbrew/.linuxbrew/bin/brew --version && \
    /home/linuxbrew/.linuxbrew/bin/brew install gcc || true; \
    else \
    echo "Skipping gcc installation - Homebrew not available"; \
    fi
USER root

# Install Hermes Agent using the official installer in non-interactive mode.
# The add-on uses an FHS-style root install: code in /usr/local/lib/hermes-agent,
# command at /usr/local/bin/hermes, data under /config/.hermes at runtime.
ENV HERMES_BUNDLED_VERSION="${HERMES_VERSION}"
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_VERSION}/scripts/install.sh -o /tmp/install-hermes.sh \
    && bash /tmp/install-hermes.sh --branch "${HERMES_VERSION}" --skip-setup --hermes-home /config/.hermes \
    && rm -f /tmp/install-hermes.sh \
    && install -d /usr/local/share \
    && hermes --version | tee /usr/local/share/hermes-bundled-version

# Hermes <= v0.18.0 rejects X-Forwarded-Prefix values longer than 64 chars
# (hermes_cli/dashboard_auth/prefix.py), but HA Supervisor ingress prefixes
# plus our /dashboard suffix are 73 chars — the prefix gets silently dropped,
# the SPA emits root-relative asset URLs, and the dashboard renders as a
# blank white page behind Ingress. Patch the cap to 200 at build time and
# verify with a realistic HA ingress prefix; the script exits non-zero
# (failing this image build) if upstream changes the code or verification
# fails. Drop this once upstream ships a fix.
COPY patch_hermes_prefix.py /tmp/patch_hermes_prefix.py
RUN python3 /tmp/patch_hermes_prefix.py /usr/local/lib/hermes-agent \
    && rm -f /tmp/patch_hermes_prefix.py

# Pre-build the Hermes dashboard web UI at image build time. The repo ships
# no prebuilt dist (hermes_cli/web_dist is gitignored), so without this the
# dashboard must run a full npm install + Vite build at container boot —
# slow, memory-hungry, and fragile on HA boxes. Building here lets run.sh
# start the dashboard with --skip-build for instant, deterministic startup.
RUN cd /usr/local/lib/hermes-agent \
    && (npm install --workspace web --silent || (cd web && npm install --silent)) \
    && (npm run build -w web || (cd web && npm run build)) \
    && test -f hermes_cli/web_dist/index.html \
    && rm -rf node_modules web/node_modules /root/.npm

# Install bundled MCP server dependencies locally inside the add-on image so the
# built-in Home Assistant MCP bridge can run without relying on user-installed packages.
RUN mkdir -p /opt/homeops-ai \
    && npm install --prefix /opt/homeops-ai @modelcontextprotocol/sdk zod

# Ship the official Hermes Paperclip adapter and Hermes Workspace UI.
RUN npm install -g "hermes-paperclip-adapter@${HERMES_PAPERCLIP_ADAPTER_VERSION}" \
    && git clone --depth 1 --branch "${HERMES_WORKSPACE_REF}" "${HERMES_WORKSPACE_REPO}" /opt/hermes-workspace \
    && cd /opt/hermes-workspace \
    && corepack enable 2>/dev/null || true \
    && npm install -g pnpm@10 \
    && pnpm install --silent \
    && NODE_OPTIONS="--max-old-space-size=3072" pnpm build

# Shell aliases and color options for interactive use
RUN tee -a /etc/bash.bashrc <<'EOF'

# Aliases
alias bat="batcat"
alias fd="fdfind"
alias homeops-onboard="/usr/local/bin/homeops-onboard"
alias homeops-configure="/usr/local/bin/homeops-configure"
alias homeops-hermes="/usr/local/bin/homeops-hermes"
alias homeops-workspace="/usr/local/bin/homeops-workspace"
alias h="/usr/local/bin/homeops-hermes"
alias homeops-report-issue="/usr/local/bin/homeops-report-issue"

# Enable colors
alias ls="ls --color=auto"
alias grep="grep --color=auto"
alias egrep="grep -E --color=auto"
alias fgrep="grep -F --color=auto"
alias diff="diff --color=auto"
alias ip="ip --color=auto"
if [ -z "${LS_COLORS+x}" ]; then
  export LS_COLORS="di=1;34:ln=1;36:so=1;pi=33:ex=1;32:bd=1;33:cd=1;33:su=1;31:sg=1;31:tw=1;34:ow=1;34"
fi
EOF
COPY run.sh /run.sh
COPY run_helpers.sh /opt/homeops-ai/run_helpers.sh
COPY hermes_config_helper.py /hermes_config_helper.py
COPY oc_config_helper.py /oc_config_helper.py
COPY render_nginx.py /render_nginx.py
COPY dashboard_api.py /dashboard_api.py
COPY homeops_router.py /homeops_router.py
COPY homeops-managed-command.sh /usr/local/bin/homeops-managed-command
COPY homeops-hermes.sh /usr/local/bin/homeops-hermes
COPY homeops-workspace.sh /usr/local/bin/homeops-workspace
COPY homeops-report-issue.sh /usr/local/bin/homeops-report-issue
COPY homeops-cleanup.sh /usr/local/bin/homeops-cleanup
COPY hermes-proxy-shim.cjs /usr/local/lib/hermes-proxy-shim.cjs
COPY ha_mcp_server.cjs /opt/homeops-ai/ha_mcp_server.cjs
COPY nginx.conf.tpl /etc/nginx/nginx.conf.tpl
COPY landing.html.tpl /etc/nginx/landing.html.tpl
COPY bootstrap-workspace /opt/homeops-ai/bootstrap-workspace
COPY bundled-skills /opt/homeops-ai/bundled-skills
RUN chmod +x /run.sh /opt/homeops-ai/run_helpers.sh /hermes_config_helper.py /oc_config_helper.py /render_nginx.py /dashboard_api.py /homeops_router.py /usr/local/bin/homeops-managed-command /usr/local/bin/homeops-hermes /usr/local/bin/homeops-workspace /usr/local/bin/homeops-report-issue /usr/local/bin/homeops-cleanup /opt/homeops-ai/ha_mcp_server.cjs \
    && ln -sf /usr/local/bin/homeops-managed-command /usr/local/bin/homeops-onboard \
    && ln -sf /usr/local/bin/homeops-managed-command /usr/local/bin/homeops-configure \
    && mkdir -p /run/nginx

CMD [ "/run.sh" ]
