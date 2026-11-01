#!/bin/sh
# Shared setup of the workspace images (infra/workspace_images.md): user `dh` uid 1000,
# /workspace, the `dexterhouse-workspace-mcp` server in its own venv, no setuid binaries.
set -eu
PYTHON="${1:-python3}"
groupadd --gid 1000 dh 2>/dev/null || true
id -u dh >/dev/null 2>&1 || useradd --uid 1000 --gid 1000 --create-home --home-dir /home/dh --shell /bin/sh dh
mkdir -p /workspace /opt/dexterhouse/lib
chown dh:dh /workspace /home/dh
"$PYTHON" -m venv /opt/dexterhouse
/opt/dexterhouse/bin/pip install --no-cache-dir --disable-pip-version-check \
    -r /tmp/dh-setup/requirements.txt
cp -r /tmp/dh-setup/dexterhouse_runner /opt/dexterhouse/lib/
cat > /usr/local/bin/dexterhouse-workspace-mcp <<'LAUNCHER'
#!/bin/sh
PYTHONPATH=/opt/dexterhouse/lib exec /opt/dexterhouse/bin/python -m dexterhouse_runner.workspace_mcp "$@"
LAUNCHER
chmod 755 /usr/local/bin/dexterhouse-workspace-mcp
ln -sf /opt/dexterhouse/bin/detect-secrets /usr/local/bin/detect-secrets
ln -sf /opt/dexterhouse/bin/detect-secrets-hook /usr/local/bin/detect-secrets-hook
# git never stores or asks for credentials in a workspace (the token is the runner's, CD-020).
git config --system credential.helper ""
git config --system init.defaultBranch main
git config --system safe.directory /workspace
# No sudo, no setuid or setgid binaries: the agents' code cannot regain privileges.
apt-get purge -y sudo 2>/dev/null || true
find / -xdev -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true
rm -rf /tmp/dh-setup /var/lib/apt/lists/* /root/.cache
