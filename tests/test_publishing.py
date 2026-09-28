"""The digest lifecycle and publishing records (migration 0003, review findings R1 and R4).

Approval belongs to one content version and is final. Publishing records are an append-only
event log whose successes carry their proof, ordered by when they happened.
"""

import sqlite3

import pytest

from conftest import sha
from customer_pulse import db

START, END = "2026-10-05T07:00:00Z", "2026-10-12T07:00:00Z"


@pytest.fixture
def run(build):
    return build.run(START, END)


def status(build, digest_id):
    return build.conn.execute(
        "SELECT status FROM digests WHERE digest_id = ?", (digest_id,)
    ).fetchone()[0]


def set_status(build, digest_id, value):
    build.conn.execute("UPDATE digests SET status = ? WHERE digest_id = ?", (value, digest_id))


def publish_doc(build, digest_id, doc="doc", commit="commit"):
    """Write and push a doc for an approved digest, then mark it published."""
    build.publish(digest_id, "doc_written", doc=doc)
    build.publish(digest_id, "doc_pushed", doc=doc, commit=commit)
    set_status(build, digest_id, "published")


# R1: approval can't be cleared or forged


def test_codex_reproduction_downgrade_then_edit_is_refused(build, run):
    digest = build.digest("dg_0001", run, approved=True)
    # Codex's exact statement breaks two rules at once (status moves back, approval is cleared).
    # SQLite doesn't define which trigger reports first, so either refusal is correct.
    either = "approval is final|status only moves forward|draft carries no approval"
    with pytest.raises(sqlite3.IntegrityError, match=either):
        build.conn.execute(
            "UPDATE digests SET status = 'draft', approved_sha256 = NULL, approved_at = NULL "
            "WHERE digest_id = ?",
            (digest,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=either):
        build.conn.execute("UPDATE digests SET status = 'draft' WHERE digest_id = ?", (digest,))
    with pytest.raises(sqlite3.IntegrityError, match="approval is final"):
        build.conn.execute(
            "UPDATE digests SET approved_sha256 = NULL, approved_at = NULL WHERE digest_id = ?",
            (digest,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="frozen once it leaves draft"):
        build.conn.execute(
            "UPDATE digests SET content_md = 'changed after approval', content_sha256 = ? "
            "WHERE digest_id = ?",
            (sha("changed after approval"), digest),
        )


def test_codex_reproduction_forged_draft_cannot_be_created_or_published(build, run):
    with pytest.raises(sqlite3.IntegrityError, match="created as an unapproved draft"):
        build.insert(
            "digests",
            digest_id="dg_0002",
            run_id=run,
            content_md="forged draft",
            content_sha256=sha("forged draft"),
            status="draft",
            approved_sha256=sha("forged draft"),
            approved_at=build.now,
            created_at=build.now,
        )
    draft = build.digest("dg_0003", run)
    with pytest.raises(sqlite3.IntegrityError, match="draft carries no approval"):
        build.conn.execute(
            "UPDATE digests SET approved_sha256 = content_sha256, approved_at = ? "
            "WHERE digest_id = ?",
            (build.now, draft),
        )
    with pytest.raises(sqlite3.IntegrityError, match="only an approved digest"):
        build.publish(draft, "doc_pushed", doc="doc", commit="c", approved=sha("# Digest dg_0003"))


@pytest.mark.parametrize(
    ("path", "illegal"),
    [
        ([], "published"),  # a draft can't skip review
        (["approved"], "draft"),
        (["approved", "superseded"], "approved"),
        (["approved", "published"], "approved"),
        (["superseded"], "draft"),
    ],
)
def test_status_only_moves_forward(build, run, path, illegal):
    digest = build.digest("dg_0001", run)
    for step in path:
        if step == "approved":
            build.approve(digest)
        elif step == "published":
            publish_doc(build, digest)
        else:
            set_status(build, digest, step)
    with pytest.raises(sqlite3.IntegrityError):
        set_status(build, digest, illegal)


def test_approval_happens_only_as_a_draft_becomes_approved(build, run):
    digest = build.digest("dg_0001", run)
    set_status(build, digest, "superseded")
    with pytest.raises(sqlite3.IntegrityError, match="only as a draft becomes approved"):
        build.conn.execute(
            "UPDATE digests SET approved_sha256 = content_sha256, approved_at = ? "
            "WHERE digest_id = ?",
            (build.now, digest),
        )


def test_the_whole_lifecycle_works_forwards(build, run):
    first = build.digest("dg_0001", run, approved=True)
    publish_doc(build, first)
    assert status(build, first) == "published"

    # A corrected version is a new draft that needs its own review before it can publish.
    second = build.digest("dg_0002", run, previous=first)
    with pytest.raises(sqlite3.IntegrityError, match="only an approved digest"):
        build.publish(second, "doc_written", doc="v2", approved=sha("# Digest dg_0002"))
    build.approve(second)
    publish_doc(build, second, doc="v2", commit="commit-2")
    set_status(build, first, "superseded")
    assert (status(build, first), status(build, second)) == ("superseded", "published")

    # History stays: superseded and published digests can't be deleted or edited.
    with pytest.raises(sqlite3.IntegrityError, match="history"):
        build.conn.execute("DELETE FROM digests WHERE digest_id = ?", (first,))


def test_drafts_can_be_regenerated_and_superseded(build, run):
    draft = build.digest("dg_0001", run)
    build.conn.execute(
        "UPDATE digests SET content_md = 'regenerated', content_sha256 = ? WHERE digest_id = ?",
        (sha("regenerated"), draft),
    )
    set_status(build, draft, "superseded")
    assert status(build, draft) == "superseded"


# R4: publishing proof is complete and its order can't be rewritten


@pytest.mark.parametrize(
    ("step", "proof"),
    [
        ("doc_written", {}),  # no document hash
        ("doc_pushed", {"doc": "doc"}),  # no team-context commit
        ("doc_pushed", {"commit": "commit"}),  # no document hash
        ("doc_listed", {"doc": "doc"}),  # no session that listed it
        ("archived", {}),  # no archive reference
    ],
)
def test_a_success_needs_its_proof(build, run, step, proof):
    digest = build.digest("dg_0001", run, approved=True)
    if step in ("doc_pushed", "doc_listed"):  # the steps a real publish would have done first
        build.publish(digest, "doc_written", doc="doc")
    if step == "doc_listed":
        build.publish(digest, "doc_pushed", doc="doc", commit="commit")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        build.publish(digest, step, **proof)


def test_failed_attempts_need_no_proof_and_retries_resume(build, run):
    digest = build.digest("dg_0001", run, approved=True)
    build.publish(digest, "doc_written", doc="doc")
    build.publish(digest, "doc_pushed", "failed", doc="doc")  # rejected push
    build.publish(digest, "doc_pushed", doc="doc", commit="commit")  # retry succeeds
    state = build.conn.execute(
        "SELECT status, attempts FROM v_publish_steps WHERE digest_id = ? AND step = 'doc_pushed'",
        (digest,),
    ).fetchone()
    assert tuple(state) == ("done", 2)


def test_a_push_must_carry_the_written_document(build, run):
    digest = build.digest("dg_0001", run, approved=True)
    build.publish(digest, "doc_written", doc="doc")
    with pytest.raises(sqlite3.IntegrityError, match="document written for this digest"):
        build.publish(digest, "doc_pushed", doc="a different doc", commit="commit")
    build.publish(digest, "doc_pushed", doc="doc", commit="commit")
    with pytest.raises(sqlite3.IntegrityError, match="document pushed for this digest"):
        build.publish(digest, "doc_listed", doc="a different doc", listed_in="fresh-session")
    build.publish(digest, "doc_listed", doc="doc", listed_in="fresh-session")


def test_publishing_needs_the_approved_hash(build, run):
    digest = build.digest("dg_0001", run, approved=True)
    with pytest.raises(sqlite3.IntegrityError, match="only an approved digest"):
        build.publish(digest, "doc_written", doc="doc", approved="b" * 64)


def test_a_digest_is_published_only_after_a_successful_push(build, run):
    digest = build.digest("dg_0001", run, approved=True)
    build.publish(digest, "doc_written", doc="doc")
    build.publish(digest, "doc_pushed", "failed", doc="doc")
    with pytest.raises(sqlite3.IntegrityError, match="only after a successful push"):
        set_status(build, digest, "published")


def test_codex_reproduction_last_published_follows_event_order(build, run):
    first = build.digest("dg_0001", run, approved=True)
    second = build.digest("dg_0002", run, previous=first, approved=True)
    build.publish(first, "doc_written", doc="one")
    build.publish(first, "doc_pushed", doc="one", commit="c1", at="2026-10-08T00:00:00Z")
    build.publish(second, "doc_written", doc="two")
    build.publish(second, "doc_pushed", doc="two", commit="c2", at="2026-10-09T00:00:00Z")

    def last():
        return build.conn.execute("SELECT digest_id FROM v_last_published_doc").fetchone()[0]

    assert last() == second
    # The old attack: touch the older success so it looks newer. Events can't be edited.
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        build.conn.execute(
            "UPDATE publish_events SET at = ? WHERE digest_id = ?",
            ("2026-10-10T00:00:00.000000Z", first),
        )
    # A later failed attempt, even with a later timestamp, doesn't change what was published.
    build.publish(first, "doc_pushed", "failed", doc="one", at="2026-10-10T00:00:00Z")
    assert last() == second
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        build.conn.execute("DELETE FROM publish_events")


def test_replacing_publish_steps_refuses_to_discard_records(db_path, clock, monkeypatch):
    shipped = db.available_migrations()
    conn = db.connect(db_path)
    monkeypatch.setattr(db, "available_migrations", lambda: shipped[:2])
    db.migrate(conn, clock)
    now = "2026-10-12T17:00:00.000000Z"
    conn.execute(
        "INSERT INTO runs (kind, mode, started_at, status) VALUES ('digest', 'offline', ?, "
        "'succeeded')",
        (now,),
    )
    conn.execute(
        "INSERT INTO digests (digest_id, run_id, content_md, content_sha256, status, "
        "approved_sha256, approved_at, created_at) VALUES ('dg_0001', 1, 'x', ?, 'approved', ?, "
        "?, ?)",
        ("a" * 64, "a" * 64, now, now),
    )
    conn.execute(
        "INSERT INTO publish_steps (digest_id, step, status, approved_sha256, updated_at) "
        "VALUES ('dg_0001', 'doc_written', 'done', ?, ?)",
        ("a" * 64, now),
    )
    monkeypatch.setattr(db, "available_migrations", lambda: shipped)
    with pytest.raises(sqlite3.IntegrityError, match="publish_steps_must_be_empty"):
        db.migrate(conn, clock)
    assert db.schema_version(conn) == 2
    assert conn.execute("SELECT count(*) FROM publish_steps").fetchone()[0] == 1
    conn.close()
