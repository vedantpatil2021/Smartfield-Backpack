#!/usr/bin/env bash
set -euo pipefail

# ── Must run as root ───────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run this script with sudo or as root." >&2
  exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

echo "==> Installing K3s..."
curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -s - \
    --disable traefik --disable servicelb

echo "==> Waiting for node to become Ready..."
until kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done
echo "    Node is Ready."

# ── Set up KUBECONFIG for the invoking user ────────────────────────────────────
echo "==> Configuring KUBECONFIG for user '$REAL_USER'..."
mkdir -p "$REAL_HOME/.kube"
cp /etc/rancher/k3s/k3s.yaml "$REAL_HOME/.kube/config"
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.kube/config"
chmod 600 "$REAL_HOME/.kube/config"

# Persist KUBECONFIG in user's shell profile if not already there
for rc in "$REAL_HOME/.bashrc" "$REAL_HOME/.zshrc"; do
  if [[ -f "$rc" ]] && ! grep -q "KUBECONFIG" "$rc"; then
    echo 'export KUBECONFIG="$HOME/.kube/config"' >> "$rc"
  fi
done

# ── Install Helm ───────────────────────────────────────────────────────────────
if command -v helm &>/dev/null; then
  echo "==> Helm already installed: $(helm version --short)"
else
  echo "==> Installing Helm..."
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  echo "    Helm installed: $(helm version --short)"
fi

# ── Model directory for WildWings ──────────────────────────────────────────────
echo "==> Creating model directory at /opt/smartfield/models/..."
mkdir -p /opt/smartfield/models
chown -R "$REAL_USER:$REAL_USER" /opt/smartfield

echo ""
echo "==> Installation complete."
echo "    Next steps:"
echo "    1. Copy yolov5su.pt to /opt/smartfield/models/"
echo "    2. Log out and back in (or run: export KUBECONFIG=\$HOME/.kube/config)"
echo "    3. Run: make deploy"
