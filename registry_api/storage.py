"""
Storage backends for Agent Registry API.

Supports in-memory (default) and PostgreSQL (via DATABASE_URL env var).
PostgreSQL uses the 'registry' schema to isolate from LiteLLM tables.
"""

import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for registry storage backends."""

    async def init_db(self) -> None: ...
    async def close(self) -> None: ...
    async def health(self) -> dict: ...

    # Generic CRUD per entity
    async def get(self, entity: str, key: str) -> Optional[dict]: ...
    async def list_all(self, entity: str) -> list[dict]: ...
    async def put(self, entity: str, key: str, value: dict) -> None: ...
    async def delete(self, entity: str, key: str) -> bool: ...
    async def exists(self, entity: str, key: str) -> bool: ...


ENTITIES = ("skills", "tools", "rag_configs", "agents", "architectures")


# ---------------------------------------------------------------------------
# In-memory storage (default fallback)
# ---------------------------------------------------------------------------

class MemoryStorage:
    """Dict-based storage matching original behavior."""

    def __init__(self):
        self._data: dict[str, dict[str, dict]] = {e: {} for e in ENTITIES}

    async def init_db(self) -> None:
        logger.info("Using in-memory storage (data lost on restart)")

    async def close(self) -> None:
        pass

    async def health(self) -> dict:
        return {
            "type": "memory",
            "status": "ok",
            "counts": {e: len(self._data[e]) for e in ENTITIES},
        }

    async def get(self, entity: str, key: str) -> Optional[dict]:
        return self._data[entity].get(key)

    async def list_all(self, entity: str) -> list[dict]:
        return list(self._data[entity].values())

    async def put(self, entity: str, key: str, value: dict) -> None:
        self._data[entity][key] = value

    async def delete(self, entity: str, key: str) -> bool:
        if key in self._data[entity]:
            del self._data[entity][key]
            return True
        return False

    async def exists(self, entity: str, key: str) -> bool:
        return key in self._data[entity]


# ---------------------------------------------------------------------------
# PostgreSQL storage
# ---------------------------------------------------------------------------

class PostgresStorage:
    """SQLAlchemy async + asyncpg backed storage using 'registry' schema."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._engine = None
        self._sessionmaker = None

    async def init_db(self) -> None:
        from sqlalchemy import Column, String, Text, text
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import DeclarativeBase, sessionmaker

        self._engine = create_async_engine(
            self._database_url,
            pool_size=5,
            max_overflow=2,
            echo=False,
        )

        class Base(DeclarativeBase):
            pass

        # All tables share the same shape: id (PK) + data (JSONB)
        for entity_name in ENTITIES:
            type(
                f"Registry_{entity_name}",
                (Base,),
                {
                    "__tablename__": entity_name,
                    "__table_args__": {"schema": "registry"},
                    "id": Column(String, primary_key=True),
                    "data": Column(Text, nullable=False),  # JSON text, cast to JSONB in DDL
                },
            )

        self._Base = Base
        self._sessionmaker = sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)

        # Create schema + tables
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS registry"))
            await conn.run_sync(Base.metadata.create_all)

        logger.info("PostgreSQL storage initialized (schema: registry)")

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()

    async def health(self) -> dict:
        from sqlalchemy import text

        try:
            async with self._sessionmaker() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
            return {"type": "postgres", "status": "ok"}
        except Exception as e:
            return {"type": "postgres", "status": "error", "error": str(e)}

    async def get(self, entity: str, key: str) -> Optional[dict]:
        import json
        from sqlalchemy import text

        async with self._sessionmaker() as session:
            result = await session.execute(
                text(f"SELECT data FROM registry.{entity} WHERE id = :id"),
                {"id": key},
            )
            row = result.scalar()
            return json.loads(row) if row else None

    async def list_all(self, entity: str) -> list[dict]:
        import json
        from sqlalchemy import text

        async with self._sessionmaker() as session:
            result = await session.execute(text(f"SELECT data FROM registry.{entity}"))
            return [json.loads(row[0]) for row in result.fetchall()]

    async def put(self, entity: str, key: str, value: dict) -> None:
        import json
        from sqlalchemy import text

        data_json = json.dumps(value)
        async with self._sessionmaker() as session:
            # Upsert
            await session.execute(
                text(
                    f"INSERT INTO registry.{entity} (id, data) VALUES (:id, :data) "
                    f"ON CONFLICT (id) DO UPDATE SET data = :data"
                ),
                {"id": key, "data": data_json},
            )
            await session.commit()

    async def delete(self, entity: str, key: str) -> bool:
        from sqlalchemy import text

        async with self._sessionmaker() as session:
            result = await session.execute(
                text(f"DELETE FROM registry.{entity} WHERE id = :id"),
                {"id": key},
            )
            await session.commit()
            return result.rowcount > 0

    async def exists(self, entity: str, key: str) -> bool:
        from sqlalchemy import text

        async with self._sessionmaker() as session:
            result = await session.execute(
                text(f"SELECT 1 FROM registry.{entity} WHERE id = :id"),
                {"id": key},
            )
            return result.scalar() is not None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

async def create_storage(database_url: Optional[str] = None) -> StorageBackend:
    """Create appropriate storage backend based on configuration."""
    if database_url:
        storage = PostgresStorage(database_url)
    else:
        logger.warning("DATABASE_URL not set — using in-memory storage (data lost on restart)")
        storage = MemoryStorage()

    await storage.init_db()
    return storage
