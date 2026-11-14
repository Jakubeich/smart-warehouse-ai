import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL", "postgresql+psycopg://warehouse:warehouse@localhost:55432/warehouse"
    )


class Repository:
    def __init__(self, url: str | None = None):
        self.engine = create_engine(url or database_url(), pool_pre_ping=True)

    def save(self, kind: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            doc = session.get(Document, (kind, key))
            if doc is None:
                doc = Document(kind=kind, id=key, payload=payload, updated_at=datetime.now(UTC))
                session.add(doc)
            else:
                doc.payload = payload
                doc.updated_at = datetime.now(UTC)
        return payload

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            doc = session.get(Document, (kind, key))
            return doc.payload if doc else None

    def list(self, kind: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            return [
                d.payload
                for d in session.scalars(
                    select(Document)
                    .where(Document.kind == kind)
                    .order_by(Document.updated_at.desc())
                )
            ]

    def delete(self, kind: str, key: str) -> bool:
        with Session(self.engine) as session, session.begin():
            doc = session.get(Document, (kind, key))
            if doc is None:
                return False
            session.delete(doc)
            return True
