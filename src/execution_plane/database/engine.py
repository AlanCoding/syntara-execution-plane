"""SQLAlchemy async engine factory with EP database TLS via connect_args."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from execution_plane.database.ssl import ssl_connect_args_from_env, strip_unsupported_asyncpg_ssl_query

if TYPE_CHECKING:
    from sqlalchemy.pool import Pool


def create_ep_engine(database_url: str, poolclass: type[Pool] | None = None) -> AsyncEngine:
    """Create an async engine, injecting asyncpg SSL connect_args from the environment."""
    url = strip_unsupported_asyncpg_ssl_query(database_url)
    connect_args = ssl_connect_args_from_env()
    if poolclass is None:
        return create_async_engine(url, connect_args=connect_args)
    return create_async_engine(url, poolclass=poolclass, connect_args=connect_args)
