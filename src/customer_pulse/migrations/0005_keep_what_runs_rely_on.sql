-- Migration 0005: rows a finished run relies on can't be deleted or replaced.
--
-- Codex's re-review (ca5cadd) found that INSERT OR REPLACE deletes a conflicting row without
-- firing DELETE triggers. It turned on recursive triggers for every connection, so replacement
-- now fires the DELETE guards. Three tables were guarded only against UPDATE, and replacement
-- still rewrote them, each time changing a finished run's facts: a signal's customer and time,
-- a run's window and status, and a used session's times. A plain DELETE could also remove a
-- signal a finished run had counted. And nothing guarded an issue's creation time, which decides
-- whether a run sees the issue at all.
--
-- Each guard below refuses a deletion, or a change to a field that never changes. Re-imports
-- still work: they update rows in place, with an UPDATE or an upsert, and the field-level rules
-- judge those.

CREATE TRIGGER signals_are_kept BEFORE DELETE ON signals
BEGIN
    SELECT RAISE (ABORT, 'signals are evidence and are kept; only a signal''s text can be revised');
END;

CREATE TRIGGER runs_are_kept BEFORE DELETE ON runs
BEGIN
    SELECT RAISE (ABORT, 'runs are kept as history');
END;

-- Reconciliation may still refresh or drop a session that no run has used.
CREATE TRIGGER sessions_are_kept_once_used BEFORE DELETE ON sessions
WHEN EXISTS (SELECT 1 FROM run_sessions WHERE session_name = OLD.session_name)
BEGIN
    SELECT RAISE (ABORT, 'a session is kept once a run has used it');
END;

CREATE TRIGGER issues_creation_is_fixed BEFORE UPDATE OF created_at ON issues
WHEN NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE (ABORT, 'an issue''s creation time is fixed');
END;

CREATE TRIGGER issues_are_kept BEFORE DELETE ON issues
BEGIN
    SELECT RAISE (ABORT, 'issues are kept as history');
END;
