#!/usr/bin/env python3
"""Provision a kind cluster and write cluster coordinates for the integration test suite.

Creates (or reuses) a kind cluster, applies the dispatcher RBAC from
``docs/feature-branch-assets/execution-plane-init.yaml``, mints a bearer
token for the ``syntara-dispatcher`` ServiceAccount, and exports the cluster
coordinates as ``EP_IT_K8S_*`` environment variables to ``$GITHUB_ENV`` (or
to stdout when ``--print`` is passed for local use).

Does not require podman, Docker, or a running EP service.  Designed for use
in GitHub Actions but also runnable locally against a throwaway cluster:

    uv run python tools/ci_kind_setup.py --print

The kind, kubectl binaries must be on PATH.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RBAC_MANIFEST = PROJECT_ROOT / "docs" / "feature-branch-assets" / "execution-plane-init.yaml"
DEFAULT_CLUSTER_NAME = "integration-test"
DEFAULT_NAMESPACE = "execution-plane"
DEFAULT_SERVICE_ACCOUNT = "syntara-dispatcher"
DEFAULT_TOKEN_TTL = "2h"  # noqa: S105  # duration string, not a credential
CONTROL_PLANE_PORT = 6443


def _run(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True, input=input_text)


def _require_binaries() -> None:
    missing = [name for name in ("kind", "kubectl") if shutil.which(name) is None]
    if missing:
        msg = f"Missing required command(s): {', '.join(missing)}"
        raise FileNotFoundError(msg)


def _kind_clusters() -> set[str]:
    result = _run(["kind", "get", "clusters"], check=False)
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def ensure_kind_cluster(name: str, *, recreate: bool) -> None:
    """Create the kind cluster, or replace it when --recreate is set."""
    exists = name in _kind_clusters()
    if exists and recreate:
        print(f"[INFO] Deleting kind cluster {name}")
        _run(["kind", "delete", "cluster", "--name", name])
        exists = False
    if exists:
        print(f"[INFO] Reusing kind cluster {name}")
        return
    print(f"[INFO] Creating kind cluster {name}")
    _run(["kind", "create", "cluster", "--name", name, "--wait", "120s"])


def export_kubeconfig(cluster_name: str, kubeconfig: Path) -> None:
    """Write a cluster-scoped kubeconfig without replacing the default file."""
    _run(["kind", "export", "kubeconfig", "--name", cluster_name, "--kubeconfig", str(kubeconfig)])


def kubectl(
    kubeconfig: Path,
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run kubectl against the kind cluster kubeconfig."""
    return _run(["kubectl", "--kubeconfig", str(kubeconfig), *args], input_text=input_text, check=check)


def apply_rbac(kubeconfig: Path) -> None:
    """Install the dispatcher namespace, ServiceAccount, and RBAC from execution-plane-init.yaml."""
    print(f"[INFO] Applying dispatcher RBAC from {RBAC_MANIFEST.relative_to(PROJECT_ROOT)}")
    kubectl(kubeconfig, "apply", "-f", str(RBAC_MANIFEST))


def service_account_token(kubeconfig: Path, namespace: str, service_account: str, duration: str) -> str:
    """Mint a bearer token for the named ServiceAccount; falls back to a bound Secret on older clusters."""
    result = kubectl(
        kubeconfig,
        "create", "token", service_account,
        "--namespace", namespace,
        "--duration", duration,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    # Fallback: bound service-account token Secret (older clusters)
    print("[INFO] kubectl create token unsupported; falling back to a bound secret")
    secret_manifest = f"""
apiVersion: v1
kind: Secret
metadata:
  name: {service_account}-token
  namespace: {namespace}
  annotations:
    kubernetes.io/service-account.name: {service_account}
type: kubernetes.io/service-account-token
"""
    kubectl(kubeconfig, "apply", "-f", "-", input_text=secret_manifest)
    for _ in range(30):
        result = kubectl(
            kubeconfig, "get", "secret", f"{service_account}-token",
            "--namespace", namespace, "-o", "json",
        )
        data = json.loads(result.stdout).get("data") or {}
        encoded = data.get("token")
        if encoded:
            return base64.b64decode(encoded).decode("ascii")
        time.sleep(1)
    msg = "Timed out waiting for a service-account token Secret"
    raise TimeoutError(msg)


def cluster_ca_pem(kubeconfig: Path) -> str:
    """Return the Kubernetes API CA as PEM text for TLS verification."""
    result = kubectl(
        kubeconfig, "config", "view", "--raw",
        "-o", "jsonpath={.clusters[0].cluster.certificate-authority-data}",
    )
    encoded = result.stdout.strip()
    if not encoded:
        msg = "kind kubeconfig has no certificate-authority-data"
        raise RuntimeError(msg)
    return base64.b64decode(encoded).decode("ascii")


def cluster_api_endpoint(kubeconfig: Path) -> str:
    """Return the API server URL from the kubeconfig."""
    result = kubectl(
        kubeconfig, "config", "view", "--minify",
        "-o", "jsonpath={.clusters[0].cluster.server}",
    )
    endpoint = result.stdout.strip()
    if not endpoint:
        msg = "Could not read the cluster API server URL from kubeconfig"
        raise RuntimeError(msg)
    return endpoint


def write_github_env(
    endpoint: str,
    token: str,
    namespace: str,
    ca_cert_pem: str,
) -> None:
    """Append EP_IT_K8S_* coordinates to $GITHUB_ENV and mask the bearer token."""
    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        print("[WARN] GITHUB_ENV not set; pass --print to display coordinates instead")
        return
    # Register the token as a secret so GitHub Actions redacts it from all
    # subsequent log output in this job.
    print(f"::add-mask::{token}")
    with Path(github_env).open("a") as fh:
        fh.write(f"EP_IT_K8S_ENDPOINT={endpoint}\n")
        fh.write(f"EP_IT_K8S_TOKEN={token}\n")
        fh.write(f"EP_IT_K8S_NAMESPACE={namespace}\n")
        fh.write(f"EP_IT_K8S_CA_CERT<<EOF\n{ca_cert_pem}\nEOF\n")
    print("[INFO] Cluster coordinates written to $GITHUB_ENV")


def print_coordinates(endpoint: str, token: str, namespace: str, ca_cert_pem: str) -> None:
    """Print a human-readable summary of the cluster coordinates (token value is hidden)."""
    print("\nCluster coordinates (export these before running the integration tests):")
    print(f"  EP_IT_K8S_ENDPOINT={endpoint}")
    print(f"  EP_IT_K8S_TOKEN=<{len(token)}-char token>")
    print(f"  EP_IT_K8S_NAMESPACE={namespace}")
    print(f"  EP_IT_K8S_CA_CERT=<{len(ca_cert_pem)}-byte PEM>")


def main() -> int:
    """Entry point: parse args, provision kind, export coordinates."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cluster-name", default=DEFAULT_CLUSTER_NAME)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument("--token-duration", default=DEFAULT_TOKEN_TTL)
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the kind cluster")
    parser.add_argument("--print", dest="print_coords", action="store_true",
                        help="Print coordinates to stdout instead of (or in addition to) GITHUB_ENV")
    args = parser.parse_args()

    kubeconfig: Path | None = None
    try:
        _require_binaries()
        ensure_kind_cluster(args.cluster_name, recreate=args.recreate)
        with tempfile.NamedTemporaryFile(prefix=f"kubeconfig-{args.cluster_name}-", delete=False) as handle:
            kubeconfig = Path(handle.name)
        export_kubeconfig(args.cluster_name, kubeconfig)
        apply_rbac(kubeconfig)
        token = service_account_token(kubeconfig, args.namespace, args.service_account, args.token_duration)
        ca_cert_pem = cluster_ca_pem(kubeconfig)
        endpoint = cluster_api_endpoint(kubeconfig)
        print(f"[INFO] Kind API endpoint: {endpoint}")
        write_github_env(endpoint, token, args.namespace, ca_cert_pem)
        if args.print_coords:
            print_coordinates(endpoint, token, args.namespace, ca_cert_pem)
    except (FileNotFoundError, RuntimeError, TimeoutError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
            print(f"Error: command failed: {' '.join(exc.cmd)}\n{detail}", file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if kubeconfig is not None:
            kubeconfig.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
