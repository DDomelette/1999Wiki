CREATE TABLE IF NOT EXISTS wiki_page_supplements (
  page_id VARCHAR(128) NOT NULL,
  source_kind VARCHAR(32) NOT NULL,
  source_key VARCHAR(512) NOT NULL,
  source_sha256 CHAR(64) NOT NULL,
  schema_version VARCHAR(32) NOT NULL,
  profile_json JSON NOT NULL,
  blocks_json JSON NOT NULL,
  diagnostics_json JSON NOT NULL,
  updated_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (page_id, source_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wiki_supplement_snapshots (
  source_kind VARCHAR(32) NOT NULL,
  source_root_digest CHAR(64) NOT NULL,
  source_count INT NOT NULL,
  matched_count INT NOT NULL,
  supplement_page_count INT NOT NULL,
  supplement_block_count INT NOT NULL,
  canonical_snapshot_sha256 CHAR(64) NOT NULL,
  schema_version VARCHAR(32) NOT NULL,
  built_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (source_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
