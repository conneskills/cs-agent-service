FROM python:3.12-slim

# System deps: Docker CLI (for container inspection), curl (health checks), Node.js (Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    # Docker CLI
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    # Node.js 22 LTS (required by Claude Code CLI)
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Install uv for fast Python dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files for dependency resolution
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy agent code
COPY agents/ agents/

# Create non-root user (Claude CLI refuses bypassPermissions as root)
RUN groupadd -r agent && useradd -r -g agent -d /app -s /bin/bash agent \
    && chown -R agent:agent /app

# Add agent user to docker group so it can access the Docker socket
RUN groupadd -f docker && usermod -aG docker agent

USER agent

EXPOSE 9100

CMD ["uv", "run", "python", "-m", "agents.devops"]
