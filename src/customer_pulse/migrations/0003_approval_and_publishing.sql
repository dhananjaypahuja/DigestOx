-- Migration 0003: a digest's approval is final, and publishing records are an append-only
-- event log whose successes carry their proof.
--
-- Review finding R1 (Codex, 95fc080): an approved digest could be downgraded to a draft with its
-- approval cleared and then edited, and a draft could carry approval fields and accept publish
-- records. Finding R4: a successful push could lack its document hash and team commit, and
-- updating an older row could reorder which push counted as the latest.

------------------------------------------------------------------------------------------------
-- The digest lifecycle
--   draft -> approved -> published, and draft, approved, or published -> superseded.
--   A digest is created as a draft. Approval happens only as the draft -> approved step, binds
--   the content hash, and is final. Content, run, and lineage are frozen once a digest leaves
--   draft, so any change means a new draft version that needs its own review.
------------------------------------------------------------------------------------------------

DROP TRIGGER digests_approved_content_is_frozen;

CREATE TRIGGER digests_start_as_drafts BEFORE INSERT ON digests
WHEN NEW.status <> 'draft' OR NEW.approved_sha256 IS NOT NULL OR NEW.approved_at IS NOT NULL
BEGIN
    SELECT RAISE (ABORT, 'a digest is created as an unapproved draft');
END;

CREATE TRIGGER digests_status_moves_forward BEFORE UPDATE OF status ON digests
WHEN NEW.status IS NOT OLD.status
 AND NOT ((OLD.status = 'draft' AND NEW.status IN ('approved', 'superseded'))
       OR (OLD.status = 'approved' AND NEW.status IN ('published', 'superseded'))
       OR (OLD.status = 'published' AND NEW.status = 'superseded'))
BEGIN
    SELECT RAISE (ABORT, 'a digest''s status only moves forward: draft, approved, published, '
                         || 'or superseded');
END;

CREATE TRIGGER digests_approve_only_a_draft BEFORE UPDATE OF approved_sha256, approved_at, status
ON digests
WHEN OLD.approved_sha256 IS NULL
 AND NEW.approved_sha256 IS NOT NULL
 AND NOT (OLD.status = 'draft' AND NEW.status = 'approved')
BEGIN
    SELECT RAISE (ABORT, 'approval happens only as a draft becomes approved');
END;

CREATE TRIGGER digests_approval_is_final BEFORE UPDATE OF approved_sha256, approved_at ON digests
WHEN OLD.approved_sha256 IS NOT NULL
 AND (NEW.approved_sha256 IS NOT OLD.approved_sha256 OR NEW.approved_at IS NOT OLD.approved_at)
BEGIN
    SELECT RAISE (ABORT, 'a digest''s approval is final; create a new draft instead');
END;

CREATE TRIGGER digests_drafts_carry_no_approval BEFORE UPDATE ON digests
WHEN NEW.status = 'draft' AND (NEW.approved_sha256 IS NOT NULL OR NEW.approved_at IS NOT NULL)
BEGIN
    SELECT RAISE (ABORT, 'a draft carries no approval');
END;

CREATE TRIGGER digests_are_frozen_after_draft
BEFORE UPDATE OF content_md, content_sha256, run_id, previous_digest_id ON digests
WHEN OLD.status <> 'draft'
 AND (NEW.content_md IS NOT OLD.content_md
      OR NEW.content_sha256 IS NOT OLD.content_sha256
      OR NEW.run_id IS NOT OLD.run_id
      OR NEW.previous_digest_id IS NOT OLD.previous_digest_id)
BEGIN
    SELECT RAISE (ABORT, 'a digest is frozen once it leaves draft; create a new draft instead');
END;

CREATE TRIGGER digests_are_kept_after_draft BEFORE DELETE ON digests
WHEN OLD.status <> 'draft'
BEGIN
    SELECT RAISE (ABORT, 'approved, published, and superseded digests are history');
END;

------------------------------------------------------------------------------------------------
-- Publishing records: an append-only event log
------------------------------------------------------------------------------------------------

-- Replacing publish_steps must never discard a record silently. Publishing isn't implemented
-- yet, so the table should be empty; if it isn't, this migration stops.
CREATE TEMP TABLE migration_0003_guard (
    publish_steps_rows INTEGER CONSTRAINT publish_steps_must_be_empty CHECK (publish_steps_rows = 0)
);
INSERT INTO migration_0003_guard SELECT count(*) FROM publish_steps;
DROP TABLE migration_0003_guard;

DROP VIEW v_last_published_doc;
DROP TABLE publish_steps;

-- One row per publishing attempt, in the order it happened (event_id). Rows are never edited or
-- removed, so neither what happened nor its order can be rewritten. A step that succeeded carries
-- its proof.
CREATE TABLE publish_events (
    event_id         INTEGER PRIMARY KEY,
    digest_id        TEXT NOT NULL REFERENCES digests (digest_id),
    step             TEXT NOT NULL
                          CHECK (step IN ('doc_written', 'doc_pushed', 'doc_listed', 'archived')),
    status           TEXT NOT NULL CHECK (status IN ('done', 'failed', 'blocked')),
    approved_sha256  TEXT NOT NULL CHECK (length(approved_sha256) = 64
                                          AND approved_sha256 NOT GLOB '*[^0-9a-f]*'),
    doc_sha256       TEXT CHECK (length(doc_sha256) = 64 AND doc_sha256 NOT GLOB '*[^0-9a-f]*'),
    team_commit      TEXT CHECK (length(team_commit) = 40 AND team_commit NOT GLOB '*[^0-9a-f]*'),
    listed_in        TEXT CHECK (listed_in <> ''),
    archive_ref      TEXT CHECK (archive_ref <> ''),
    detail_json      TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(detail_json)),
    at               TEXT NOT NULL CHECK (at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (status <> 'done' OR step <> 'doc_written' OR doc_sha256 IS NOT NULL),
    CHECK (status <> 'done' OR step <> 'doc_pushed'
           OR (doc_sha256 IS NOT NULL AND team_commit IS NOT NULL)),
    CHECK (status <> 'done' OR step <> 'doc_listed'
           OR (doc_sha256 IS NOT NULL AND listed_in IS NOT NULL)),
    CHECK (status <> 'done' OR step <> 'archived' OR archive_ref IS NOT NULL)
) STRICT;

CREATE INDEX publish_events_by_digest ON publish_events (digest_id, step, event_id);

CREATE TRIGGER publish_events_are_append_only_update BEFORE UPDATE ON publish_events
BEGIN
    SELECT RAISE (ABORT, 'publish events are append-only');
END;

CREATE TRIGGER publish_events_are_append_only_delete BEFORE DELETE ON publish_events
BEGIN
    SELECT RAISE (ABORT, 'publish events are append-only');
END;

-- Only an approved (or already published) digest can be published, and only its approved hash.
CREATE TRIGGER publish_events_need_an_approved_digest BEFORE INSERT ON publish_events
WHEN (SELECT status FROM digests WHERE digest_id = NEW.digest_id) NOT IN ('approved', 'published')
  OR NEW.approved_sha256 IS NOT (SELECT approved_sha256 FROM digests
                                 WHERE digest_id = NEW.digest_id)
BEGIN
    SELECT RAISE (ABORT, 'only an approved digest''s approved content can be published');
END;

-- A push proves the document that was written; a listing proves the document that was pushed.
-- These rules judge only approved digests and records that carry a document hash, so each
-- failure has one owner: the trigger above rejects unapproved digests, and the CHECK
-- constraints reject successes that lack their proof.
CREATE TRIGGER publish_events_push_what_was_written BEFORE INSERT ON publish_events
WHEN NEW.step = 'doc_pushed' AND NEW.status = 'done' AND NEW.doc_sha256 IS NOT NULL
 AND (SELECT status FROM digests WHERE digest_id = NEW.digest_id) IN ('approved', 'published')
 AND NOT EXISTS (SELECT 1 FROM publish_events
                 WHERE digest_id = NEW.digest_id AND step = 'doc_written'
                   AND status = 'done' AND doc_sha256 = NEW.doc_sha256)
BEGIN
    SELECT RAISE (ABORT, 'a push must carry the hash of a document written for this digest');
END;

CREATE TRIGGER publish_events_list_what_was_pushed BEFORE INSERT ON publish_events
WHEN NEW.step = 'doc_listed' AND NEW.status = 'done' AND NEW.doc_sha256 IS NOT NULL
 AND (SELECT status FROM digests WHERE digest_id = NEW.digest_id) IN ('approved', 'published')
 AND NOT EXISTS (SELECT 1 FROM publish_events
                 WHERE digest_id = NEW.digest_id AND step = 'doc_pushed'
                   AND status = 'done' AND doc_sha256 = NEW.doc_sha256)
BEGIN
    SELECT RAISE (ABORT, 'a listing must carry the hash of a document pushed for this digest');
END;

-- A digest is "published" only once a push of it has succeeded.
CREATE TRIGGER digests_published_needs_a_push BEFORE UPDATE OF status ON digests
WHEN NEW.status = 'published' AND OLD.status <> 'published'
 AND NOT EXISTS (SELECT 1 FROM publish_events
                 WHERE digest_id = NEW.digest_id AND step = 'doc_pushed' AND status = 'done')
BEGIN
    SELECT RAISE (ABORT, 'a digest is published only after a successful push');
END;

-- Each step's current state: its latest event.
CREATE VIEW v_publish_steps AS
SELECT e.digest_id, e.step, e.status, e.approved_sha256, e.doc_sha256, e.team_commit,
       e.listed_in, e.archive_ref, e.at, e.event_id,
       (SELECT count(*) FROM publish_events AS n
        WHERE n.digest_id = e.digest_id AND n.step = e.step) AS attempts
FROM publish_events AS e
WHERE e.event_id = (SELECT max(e2.event_id) FROM publish_events AS e2
                    WHERE e2.digest_id = e.digest_id AND e2.step = e.step);

-- What Pulse last pushed to the team doc, by event order, for the ownership check.
CREATE VIEW v_last_published_doc AS
SELECT e.digest_id, e.doc_sha256, e.team_commit, e.at, e.event_id
FROM publish_events AS e
WHERE e.step = 'doc_pushed' AND e.status = 'done'
ORDER BY e.event_id DESC
LIMIT 1;
