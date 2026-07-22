SET @wiki_media_column_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'wiki_page_supplements'
    AND column_name = 'media_links_json'
);

SET @wiki_media_column_sql = IF(
  @wiki_media_column_exists = 0,
  'ALTER TABLE wiki_page_supplements ADD COLUMN media_links_json JSON NULL AFTER diagnostics_json',
  'SELECT 1'
);

PREPARE wiki_media_column_stmt FROM @wiki_media_column_sql;
EXECUTE wiki_media_column_stmt;
DEALLOCATE PREPARE wiki_media_column_stmt;
