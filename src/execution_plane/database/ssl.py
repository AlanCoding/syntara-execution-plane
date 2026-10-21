"""SSL/TLS context construction for PostgreSQL connections.

The SQLAlchemy asyncpg dialect forwards leftover URL query keys to
:func:`asyncpg.connect`, which does **not** accept libpq parameters such as
``sslmode``, ``sslrootcert``, ``sslcert``, or ``sslkey``. TLS must go through
``connect_args={"ssl": ...}`` (and the equivalent kwargs for raw asyncpg).
"""

from __future__ import annotations

import os
import ssl
from typing import Any

from sqlalchemy.engine import make_url

_MODES_NEEDING_CONTEXT = frozenset({"verify-ca", "verify-full"})
_MODES_PASSTHROUGH = frozenset({"disable", "allow", "require"})
_UNSUPPORTED_ASYNCPG_SSL_QUERY_KEYS = frozenset({"sslmode", "sslrootcert", "sslcert", "sslkey"})

_DEFAULT_SSL_MODE = "prefer"


def strip_unsupported_asyncpg_ssl_query(database_url: str) -> str:
    """Drop libpq SSL query keys that asyncpg rejects from *database_url*."""
    parsed = make_url(database_url)
    query = {
        key: value for key, value in parsed.query.items() if key.lower() not in _UNSUPPORTED_ASYNCPG_SSL_QUERY_KEYS
    }
    return parsed.set(query=query).render_as_string(hide_password=False)


def build_ssl_connect_args(
    *,
    ssl_mode: str,
    ssl_root_cert: str | None = None,
    ssl_cert: str | None = None,
    ssl_key: str | None = None,
) -> dict[str, Any]:
    """Build the ``connect_args`` dict for asyncpg SSL connections.

    Mapping from PostgreSQL ``sslmode``:

    * ``prefer`` — empty dict; asyncpg defaults to prefer when ``ssl`` is omitted.
    * ``disable`` / ``allow`` / ``require`` without client certificates — the
      mode string is passed as ``{"ssl": "<mode>"}``.
    * ``require`` with client certificates — an :class:`ssl.SSLContext` with
      ``CERT_NONE`` (encrypt only).
    * ``verify-ca`` — ``CERT_REQUIRED`` and ``check_hostname=False``.
    * ``verify-full`` — ``CERT_REQUIRED`` and ``check_hostname=True``.
    """
    has_client_certs = ssl_cert is not None

    if ssl_mode == "prefer":
        return {}

    if ssl_mode in _MODES_PASSTHROUGH and not has_client_certs:
        return {"ssl": ssl_mode}

    if ssl_mode in _MODES_NEEDING_CONTEXT or ssl_mode in _MODES_PASSTHROUGH:
        return {"ssl": _build_context(ssl_mode, ssl_root_cert, ssl_cert, ssl_key)}

    msg = f"Unknown SSL mode: {ssl_mode!r}"
    raise ValueError(msg)


def ssl_connect_args_from_env() -> dict[str, Any]:
    """Build asyncpg SSL connect args from ``EP_DB_SSL_*`` environment variables."""
    return build_ssl_connect_args(
        ssl_mode=os.environ.get("EP_DB_SSL_MODE", _DEFAULT_SSL_MODE).lower(),
        ssl_root_cert=_optional_env("EP_DB_SSL_ROOT_CERT"),
        ssl_cert=_optional_env("EP_DB_SSL_CERT"),
        ssl_key=_optional_env("EP_DB_SSL_KEY"),
    )


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return value


def _verified_client_context() -> ssl.SSLContext:
    """TLS client context with hostname verification and a required certificate."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _build_context(
    ssl_mode: str,
    ssl_root_cert: str | None,
    ssl_cert: str | None,
    ssl_key: str | None,
) -> ssl.SSLContext:
    if ssl_mode == "require":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif ssl_mode == "verify-ca":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
    else:
        ctx = _verified_client_context()

    if ssl_root_cert is not None:
        ctx.load_verify_locations(cafile=ssl_root_cert)

    if ssl_cert is not None:
        ctx.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)

    return ctx
