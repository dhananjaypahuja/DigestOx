-- Migration 0004: merges can't form cycles, and resolution never drops a theme silently.
--
-- Review finding R3 (Codex, 95fc080): A -> B followed by B -> A succeeded. Resolution starts from
-- themes that were never merged, so a cycle resolved to nothing and its assignments vanished from
-- every fact view. Resolution also stopped silently at a chain depth of 64.
--
-- The rules below make a cycle impossible. A theme can merge only into an active theme, and a
-- merge is final. Closing a cycle needs a merge into a theme that is already merged, which is
-- refused. Chains still form, legitimately, when a theme that others merged into later merges
-- itself, and resolution follows them to any depth.

------------------------------------------------------------------------------------------------
-- Resolution, and a check that it covers every theme
------------------------------------------------------------------------------------------------

DROP VIEW v_theme_resolution;

-- Each theme mapped to the theme that survives it after merges (itself if never merged). The
-- recursion walks down from surviving themes, so it terminates without a depth limit.
CREATE VIEW v_theme_resolution AS
WITH RECURSIVE chain (theme_id, final_theme_id) AS (
    SELECT theme_id, theme_id FROM themes WHERE merged_into IS NULL
    UNION
    SELECT t.theme_id, chain.final_theme_id
    FROM themes AS t
    JOIN chain ON t.merged_into = chain.theme_id
)
SELECT theme_id, final_theme_id FROM chain;

-- Themes resolution can't reach. Only a merge cycle produces one, so this must always be empty.
CREATE VIEW v_theme_unresolved AS
SELECT t.theme_id
FROM themes AS t
WHERE NOT EXISTS (SELECT 1 FROM v_theme_resolution AS r WHERE r.theme_id = t.theme_id);

-- A database that already holds a cycle stops here rather than being accepted silently.
CREATE TEMP TABLE migration_0004_guard (
    unresolved_themes INTEGER CONSTRAINT themes_must_have_no_merge_cycles
                      CHECK (unresolved_themes = 0)
);
INSERT INTO migration_0004_guard SELECT count(*) FROM v_theme_unresolved;
DROP TABLE migration_0004_guard;

------------------------------------------------------------------------------------------------
-- Merge and split rules
------------------------------------------------------------------------------------------------

CREATE TRIGGER themes_merge_only_into_an_active_theme_insert BEFORE INSERT ON themes
WHEN NEW.merged_into IS NOT NULL
 AND (SELECT status FROM themes WHERE theme_id = NEW.merged_into) IS NOT 'active'
BEGIN
    SELECT RAISE (ABORT, 'a theme can merge only into an active theme');
END;

CREATE TRIGGER themes_merge_only_into_an_active_theme_update BEFORE UPDATE OF merged_into ON themes
WHEN NEW.merged_into IS NOT NULL
 AND NEW.merged_into IS NOT OLD.merged_into
 AND (SELECT status FROM themes WHERE theme_id = NEW.merged_into) IS NOT 'active'
BEGIN
    SELECT RAISE (ABORT, 'a theme can merge only into an active theme');
END;

CREATE TRIGGER themes_merge_only_an_active_theme BEFORE UPDATE OF merged_into ON themes
WHEN OLD.merged_into IS NULL AND NEW.merged_into IS NOT NULL AND OLD.status <> 'active'
BEGIN
    SELECT RAISE (ABORT, 'only an active theme can be merged');
END;

CREATE TRIGGER themes_merges_are_final BEFORE UPDATE OF merged_into, status ON themes
WHEN OLD.merged_into IS NOT NULL
 AND (NEW.merged_into IS NOT OLD.merged_into OR NEW.status IS NOT OLD.status)
BEGIN
    SELECT RAISE (ABORT, 'a merge is final');
END;

CREATE TRIGGER themes_split_only_from_an_active_theme BEFORE INSERT ON themes
WHEN NEW.split_from IS NOT NULL
 AND (SELECT status FROM themes WHERE theme_id = NEW.split_from) IS NOT 'active'
BEGIN
    SELECT RAISE (ABORT, 'a theme can split only from an active theme');
END;

CREATE TRIGGER themes_split_lineage_is_fixed BEFORE UPDATE OF split_from ON themes
WHEN NEW.split_from IS NOT OLD.split_from
BEGIN
    SELECT RAISE (ABORT, 'a theme''s split lineage is fixed');
END;

CREATE TRIGGER themes_are_kept BEFORE DELETE ON themes
BEGIN
    SELECT RAISE (ABORT, 'themes are kept for their stable IDs; retire a theme instead');
END;
