from __future__ import annotations

import sqlite3

import pytest

from core.schemas.fingpt import FinGPTAnnotation
from pipelines.data_mart.storage import db as storage_db
from pipelines.data_mart.storage.db import connect, init_db
from pipelines.data_mart.storage.repository import get_fingpt_annotations, upsert_fingpt_annotations
from pipelines.data_mart.storage.schema import SCHEMA_VERSION


def _conn(tmp_path):
    db_path = tmp_path / "research_mart.db"
    init_db(db_path)
    return connect(db_path)


def test_fingpt_annotations_schema_columns_primary_key_and_indexes(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(fingpt_article_annotations)")}
        indexes = {row["name"]: row for row in conn.execute("PRAGMA index_list(fingpt_article_annotations)")}
        ticker_task_index = [
            row
            for row in conn.execute("PRAGMA index_xinfo(idx_fingpt_annotations_ticker_task)")
            if row["key"]
        ]
        article_index = [
            row
            for row in conn.execute("PRAGMA index_xinfo(idx_fingpt_annotations_article)")
            if row["key"]
        ]

    assert list(columns) == [
        "article_id",
        "ticker",
        "task",
        "label",
        "confidence",
        "source",
        "model_id",
        "metadata_json",
        "created_at",
    ]
    assert columns["article_id"]["type"] == "TEXT"
    assert columns["article_id"]["notnull"] == 1
    assert columns["article_id"]["pk"] == 1
    assert columns["ticker"]["type"] == "TEXT"
    assert columns["ticker"]["notnull"] == 0
    assert columns["task"]["type"] == "TEXT"
    assert columns["task"]["notnull"] == 1
    assert columns["task"]["pk"] == 2
    assert columns["label"]["type"] == "TEXT"
    assert columns["label"]["notnull"] == 1
    assert columns["confidence"]["type"] == "REAL"
    assert columns["confidence"]["notnull"] == 1
    assert columns["confidence"]["dflt_value"] == "0.0"
    assert columns["source"]["type"] == "TEXT"
    assert columns["source"]["notnull"] == 1
    assert columns["source"]["dflt_value"] == "'fingpt'"
    assert columns["source"]["pk"] == 3
    assert columns["model_id"]["type"] == "TEXT"
    assert columns["model_id"]["notnull"] == 1
    assert columns["model_id"]["dflt_value"] == "''"
    assert columns["model_id"]["pk"] == 4
    assert columns["metadata_json"]["type"] == "TEXT"
    assert columns["metadata_json"]["notnull"] == 1
    assert columns["metadata_json"]["dflt_value"] == "'{}'"
    assert columns["created_at"]["type"] == "TEXT"
    assert columns["created_at"]["notnull"] == 1

    assert indexes["idx_fingpt_annotations_ticker_task"]["unique"] == 0
    assert indexes["idx_fingpt_annotations_article"]["unique"] == 0
    assert [(row["name"], row["desc"]) for row in ticker_task_index] == [
        ("ticker", 0),
        ("task", 0),
        ("created_at", 1),
    ]
    assert [(row["name"], row["desc"]) for row in article_index] == [("article_id", 0)]


def test_fingpt_annotations_schema_version_is_incremented() -> None:
    assert SCHEMA_VERSION == 6


def test_init_db_migrates_nullable_model_id_annotation_table(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE fingpt_article_annotations (
                article_id TEXT NOT NULL,
                ticker TEXT,
                task TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                source TEXT NOT NULL DEFAULT 'fingpt',
                model_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                PRIMARY KEY (article_id, task, source, model_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fingpt_article_annotations(
                article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at
            )
            VALUES ('article-1', 'AAPL', 'sentiment', 'old-label', 0.3, 'fingpt', NULL, '{"rank":1}', '2026-05-08T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO fingpt_article_annotations(
                article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at
            )
            VALUES ('article-1', 'AAPL', 'sentiment', 'new-label', 0.9, 'fingpt', NULL, '{"rank":2}', '2026-05-08T02:00:00Z')
            """
        )
        conn.commit()

    init_db(db_path)

    with connect(db_path) as conn:
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(fingpt_article_annotations)")}
        raw_rows = conn.execute(
            """
            SELECT article_id, label, confidence, model_id, metadata_json, created_at
            FROM fingpt_article_annotations
            WHERE article_id='article-1'
            """
        ).fetchall()
        annotations = get_fingpt_annotations(conn)

    assert columns["model_id"]["notnull"] == 1
    assert columns["model_id"]["dflt_value"] == "''"
    assert len(raw_rows) == 1
    assert raw_rows[0]["model_id"] == ""
    assert raw_rows[0]["label"] == "new-label"
    assert raw_rows[0]["created_at"] == "2026-05-08T02:00:00Z"
    assert len(annotations) == 1
    assert annotations[0].label == "new-label"
    assert annotations[0].model_id == ""
    assert annotations[0].metadata == {"rank": 2}


def test_init_db_annotation_migration_failure_rolls_back_rebuild(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "research_mart.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE fingpt_article_annotations (
                article_id TEXT NOT NULL,
                ticker TEXT,
                task TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                source TEXT NOT NULL DEFAULT 'fingpt',
                model_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                PRIMARY KEY (article_id, task, source, model_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fingpt_article_annotations(
                article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at
            )
            VALUES ('article-1', 'AAPL', 'sentiment', 'old-label', 0.3, 'fingpt', NULL, '{"rank":1}', '2026-05-08T00:00:00Z')
            """
        )
        conn.commit()

    def fail_copy(conn, model_expr):  # noqa: ARG001
        raise RuntimeError("forced migration copy failure")

    monkeypatch.setattr(storage_db, "_copy_fingpt_annotations_rows", fail_copy)
    with pytest.raises(RuntimeError, match="forced migration copy failure"):
        storage_db.init_db(db_path)
    monkeypatch.undo()

    with connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(fingpt_article_annotations)")}
        rows = conn.execute("SELECT label, model_id FROM fingpt_article_annotations").fetchall()

    assert "fingpt_article_annotations" in tables
    assert "fingpt_article_annotations_old" not in tables
    assert columns["model_id"]["notnull"] == 0
    assert len(rows) == 1
    assert rows[0]["label"] == "old-label"
    assert rows[0]["model_id"] is None

    init_db(db_path)

    with connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(fingpt_article_annotations)")}
        annotations = get_fingpt_annotations(conn)

    assert "fingpt_article_annotations_old" not in tables
    assert columns["model_id"]["notnull"] == 1
    assert columns["model_id"]["dflt_value"] == "''"
    assert len(annotations) == 1
    assert annotations[0].label == "old-label"
    assert annotations[0].model_id == ""


def test_model_id_is_not_null_and_repository_stores_empty_default(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO fingpt_article_annotations(
                    article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at
                )
                VALUES ('raw-null', 'AAPL', 'sentiment', 'positive', 0.7, 'fingpt', NULL, '{}', '2026-05-08T00:00:00Z')
                """
            )
        conn.rollback()

        upsert_fingpt_annotations(
            conn,
            [FinGPTAnnotation(article_id="article-1", ticker="AAPL", task="sentiment", label="positive")],
        )
        stored = conn.execute(
            "SELECT model_id FROM fingpt_article_annotations WHERE article_id='article-1'"
        ).fetchone()["model_id"]

    assert stored == ""


def test_upsert_and_get_fingpt_annotations(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        inserted = upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="aapl",
                    task="sentiment",
                    label="positive",
                    confidence=0.91,
                    model_id="fingpt-sentiment",
                    metadata={"reason": "earnings beat", "score": 3},
                )
            ],
        )

        rows = get_fingpt_annotations(conn)

    assert inserted == 1
    assert len(rows) == 1
    assert rows[0].article_id == "article-1"
    assert rows[0].ticker == "AAPL"
    assert rows[0].task == "sentiment"
    assert rows[0].label == "positive"
    assert rows[0].confidence == 0.91
    assert rows[0].source == "fingpt"
    assert rows[0].model_id == "fingpt-sentiment"
    assert rows[0].metadata == {"reason": "earnings beat", "score": 3}


def test_annotation_metadata_json_preserves_unicode_and_sorts_keys(tmp_path) -> None:
    accent = chr(233)
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="AAPL",
                    task="sentiment",
                    label="positive",
                    metadata={"zeta": 3, "alpha": f"caf{accent}", "middle": {"b": 2, "a": 1}},
                )
            ],
        )

        raw = conn.execute(
            "SELECT metadata_json FROM fingpt_article_annotations WHERE article_id='article-1'"
        ).fetchone()["metadata_json"]

    assert raw == f'{{"alpha":"caf{accent}","middle":{{"a":1,"b":2}},"zeta":3}}'
    assert "\\u00e9" not in raw


def test_annotation_upsert_replaces_same_article_task_model(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="MSFT",
                    task="sentiment",
                    label="neutral",
                    confidence=0.4,
                    model_id="model-a",
                    metadata={"version": 1},
                )
            ],
        )
        replaced = upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="msft",
                    task="sentiment",
                    label="negative",
                    confidence=0.82,
                    model_id="model-a",
                    metadata={"version": 2},
                )
            ],
        )

        rows = get_fingpt_annotations(conn)

    assert replaced == 1
    assert len(rows) == 1
    assert rows[0].ticker == "MSFT"
    assert rows[0].label == "negative"
    assert rows[0].confidence == 0.82
    assert rows[0].metadata == {"version": 2}


def test_upsert_fingpt_annotations_does_not_commit_and_allows_rollback(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    init_db(db_path)

    conn = connect(db_path)
    try:
        upsert_fingpt_annotations(
            conn,
            [FinGPTAnnotation(article_id="article-1", ticker="AAPL", task="sentiment", label="positive")],
        )
        assert len(get_fingpt_annotations(conn)) == 1

        conn.rollback()

        assert get_fingpt_annotations(conn) == []
    finally:
        conn.close()


def test_get_fingpt_annotations_supports_plain_sqlite_tuple_rows(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="aapl",
                    task="sentiment",
                    label="positive",
                    model_id="plain-sqlite",
                    metadata={"source": "tuple-row"},
                )
            ],
        )

        rows = get_fingpt_annotations(conn, ticker="AAPL")
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0].article_id == "article-1"
    assert rows[0].ticker == "AAPL"
    assert rows[0].model_id == "plain-sqlite"
    assert rows[0].metadata == {"source": "tuple-row"}


def test_annotation_source_and_model_id_are_part_of_identity(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="AAPL",
                    task="sentiment",
                    label="positive",
                    source="fingpt",
                    model_id="model-a",
                ),
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="AAPL",
                    task="sentiment",
                    label="negative",
                    source="fingpt-alt",
                    model_id="model-a",
                ),
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="AAPL",
                    task="sentiment",
                    label="neutral",
                    source="fingpt",
                    model_id="model-b",
                ),
            ],
        )
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id="article-1",
                    ticker="AAPL",
                    task="sentiment",
                    label="replaced",
                    source="fingpt",
                    model_id="model-a",
                )
            ],
        )

        rows = conn.execute(
            """
            SELECT source, model_id, label
            FROM fingpt_article_annotations
            WHERE article_id='article-1' AND task='sentiment'
            ORDER BY source, model_id
            """
        ).fetchall()

    assert [(row["source"], row["model_id"], row["label"]) for row in rows] == [
        ("fingpt", "model-a", "replaced"),
        ("fingpt", "model-b", "neutral"),
        ("fingpt-alt", "model-a", "negative"),
    ]


def test_get_fingpt_annotations_filters_ticker_and_task(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(article_id="article-1", ticker="aapl", task="sentiment", label="positive"),
                FinGPTAnnotation(article_id="article-2", ticker="AAPL", task="headline", label="earnings"),
                FinGPTAnnotation(article_id="article-3", ticker="MSFT", task="sentiment", label="neutral"),
            ],
        )

        rows = get_fingpt_annotations(conn, ticker="aapl", task="sentiment", limit=10)

    assert [row.article_id for row in rows] == ["article-1"]
    assert rows[0].ticker == "AAPL"
    assert rows[0].task == "sentiment"


def test_get_fingpt_annotations_bounds_limit(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(
                    article_id=f"article-{index:04d}",
                    ticker="AAPL",
                    task="sentiment",
                    label="positive",
                    model_id="limit-test",
                )
                for index in range(1001)
            ],
        )

        one_row = get_fingpt_annotations(conn, limit=0)
        thousand_rows = get_fingpt_annotations(conn, limit=5000)

    assert len(one_row) == 1
    assert len(thousand_rows) == 1000


def test_get_fingpt_annotations_orders_newest_first(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        upsert_fingpt_annotations(
            conn,
            [
                FinGPTAnnotation(article_id="old", ticker="AAPL", task="sentiment", label="old"),
                FinGPTAnnotation(article_id="new", ticker="AAPL", task="sentiment", label="new"),
                FinGPTAnnotation(article_id="middle", ticker="AAPL", task="sentiment", label="middle"),
            ],
        )
        conn.execute(
            """
            UPDATE fingpt_article_annotations
            SET created_at = CASE article_id
                WHEN 'old' THEN '2026-05-08T00:00:00Z'
                WHEN 'middle' THEN '2026-05-08T01:00:00Z'
                WHEN 'new' THEN '2026-05-08T02:00:00Z'
            END
            """
        )
        conn.commit()

        rows = get_fingpt_annotations(conn, ticker="AAPL", task="sentiment")

    assert [row.article_id for row in rows] == ["new", "middle", "old"]


def test_get_fingpt_annotations_tolerates_bad_metadata_json(tmp_path) -> None:
    with _conn(tmp_path) as conn:
        conn.execute(
            """
            INSERT INTO fingpt_article_annotations(
                article_id, ticker, task, label, confidence, source, model_id, metadata_json, created_at
            )
            VALUES ('article-1', 'AAPL', 'sentiment', 'positive', 0.7, 'fingpt', 'model-a', '{bad-json', '2026-05-08T00:00:00Z')
            """
        )
        conn.commit()

        rows = get_fingpt_annotations(conn)

    assert len(rows) == 1
    assert rows[0].metadata == {"raw": "{bad-json"}
