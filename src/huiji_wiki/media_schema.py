"""MySQL schema used by the Wiki media v3 compatibility layer."""

CREATE_MEDIA_RESOURCES_SQL = """
CREATE TABLE IF NOT EXISTS wiki_media_resources (
  resource_id VARCHAR(80) NOT NULL PRIMARY KEY,
  media_id VARCHAR(64) NOT NULL,
  asset_type VARCHAR(64) NOT NULL,
  mime VARCHAR(127) NOT NULL,
  filename VARCHAR(512) NOT NULL,
  source_url TEXT NOT NULL,
  url TEXT NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  is_available BOOLEAN NOT NULL,
  is_common BOOLEAN NOT NULL,
  content_hash CHAR(64) NOT NULL,
  quality_flags_json JSON NOT NULL,
  sha1 CHAR(40) NOT NULL,
  source_sha1 CHAR(40) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  size BIGINT UNSIGNED NOT NULL,
  duration_ms BIGINT UNSIGNED NOT NULL,
  width BIGINT UNSIGNED NOT NULL,
  height BIGINT UNSIGNED NOT NULL,
  KEY idx_wiki_media_resources_media_id (media_id),
  KEY idx_wiki_media_resources_sha1 (sha1),
  UNIQUE KEY uq_wiki_media_resources_content_sha256 (content_sha256)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

CREATE_MEDIA_BINDINGS_SQL = """
CREATE TABLE IF NOT EXISTS wiki_media_bindings (
  binding_id VARCHAR(80) NOT NULL PRIMARY KEY,
  resource_id VARCHAR(80) NOT NULL,
  page_id VARCHAR(128) NOT NULL,
  entity_id VARCHAR(128) NOT NULL,
  entity_name VARCHAR(255) NOT NULL,
  owner_entity_id VARCHAR(255) NOT NULL,
  owner_page_id VARCHAR(255) NOT NULL,
  parent_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  section_key VARCHAR(64) NOT NULL,
  media_role VARCHAR(64) NOT NULL,
  variant VARCHAR(128) NOT NULL,
  skin_id VARCHAR(128) NOT NULL,
  event_name VARCHAR(255) NOT NULL,
  language VARCHAR(32) NOT NULL,
  source_binding_token VARCHAR(255) NOT NULL,
  source_refs_json JSON NOT NULL,
  title VARCHAR(255) NOT NULL,
  attach_policy VARCHAR(64) NOT NULL,
  search_text TEXT NOT NULL,
  panel_group VARCHAR(64) NOT NULL,
  sort_order BIGINT UNSIGNED NOT NULL,
  binding_status VARCHAR(32) NOT NULL,
  KEY idx_wiki_media_bindings_page (page_id, sort_order),
  KEY idx_wiki_media_bindings_resource (resource_id),
  KEY idx_wiki_media_bindings_owner_page (owner_page_id),
  KEY idx_wiki_media_bindings_parent (parent_id),
  CONSTRAINT fk_wiki_media_binding_resource
    FOREIGN KEY (resource_id) REFERENCES wiki_media_resources(resource_id)
    ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

DROP_MEDIA_BINDINGS_SQL = "DROP TABLE IF EXISTS wiki_media_bindings"
DROP_MEDIA_RESOURCES_SQL = "DROP TABLE IF EXISTS wiki_media_resources"


def media_v3_schema_statements() -> tuple[str, str]:
    return CREATE_MEDIA_RESOURCES_SQL, CREATE_MEDIA_BINDINGS_SQL
