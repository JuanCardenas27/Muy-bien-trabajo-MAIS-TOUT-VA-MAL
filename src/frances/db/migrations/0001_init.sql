PRAGMA foreign_keys = ON;
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE courses (id TEXT PRIMARY KEY, name TEXT NOT NULL, section TEXT, state TEXT NOT NULL,
  alternate_link TEXT, update_time TEXT NOT NULL, included INTEGER NOT NULL DEFAULT 1, raw_json TEXT NOT NULL);
CREATE TABLE topics (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
  name TEXT NOT NULL, update_time TEXT NOT NULL);
CREATE TABLE items (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
  kind TEXT NOT NULL CHECK (kind IN ('coursework','material','announcement')), classroom_id TEXT NOT NULL,
  topic_id TEXT, title TEXT, text TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, alternate_link TEXT,
  creation_time TEXT NOT NULL, update_time TEXT NOT NULL, due_at TEXT, content_hash TEXT NOT NULL,
  raw_json TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, deleted_at TEXT,
  UNIQUE (kind, classroom_id));
CREATE TABLE blobs (sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, mime_type TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE attachments (id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id),
  kind TEXT NOT NULL CHECK (kind IN ('drive_file','link','youtube','form')), external_id TEXT NOT NULL,
  title TEXT, url TEXT, mime_type TEXT, drive_version TEXT,
  blob_sha256 TEXT REFERENCES blobs(sha256), export_pdf_sha256 TEXT REFERENCES blobs(sha256),
  export_text_sha256 TEXT REFERENCES blobs(sha256),
  status TEXT NOT NULL CHECK (status IN ('pending','downloaded','reference','skipped_too_large','forbidden','not_found','error')),
  error TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, removed_at TEXT,
  UNIQUE (item_id, kind, external_id));
CREATE TABLE watermarks (course_id TEXT NOT NULL, stream TEXT NOT NULL, last_update_time TEXT NOT NULL,
  last_run_at TEXT NOT NULL, PRIMARY KEY (course_id, stream));
CREATE TABLE extractions (blob_sha256 TEXT NOT NULL REFERENCES blobs(sha256), extractor_version TEXT NOT NULL,
  method TEXT NOT NULL, lang TEXT NOT NULL, char_count INTEGER NOT NULL, path TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (blob_sha256, extractor_version));
CREATE TABLE generations (item_id TEXT PRIMARY KEY REFERENCES items(id), input_hash TEXT NOT NULL,
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE cards (id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('vocab','phrase','grammar','conjugation','drill')),
  front_fr TEXT NOT NULL, back_es TEXT NOT NULL, example_fr TEXT, example_es TEXT, notes TEXT,
  ipa TEXT, phonemes TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]',
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE card_sources (card_id TEXT NOT NULL REFERENCES cards(id), item_id TEXT NOT NULL REFERENCES items(id),
  PRIMARY KEY (card_id, item_id));
CREATE TABLE sheets (item_id TEXT PRIMARY KEY REFERENCES items(id), json TEXT NOT NULL,
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE audio (cache_key TEXT PRIMARY KEY, text TEXT NOT NULL, text_norm TEXT NOT NULL,
  voice_id TEXT NOT NULL, family TEXT NOT NULL, family_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','done','failed','failed_qa')), engine_used TEXT,
  path TEXT, duration_ms INTEGER, qa_cer REAL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
  updated_at TEXT NOT NULL);
CREATE TABLE card_audio (card_id TEXT NOT NULL REFERENCES cards(id),
  field TEXT NOT NULL CHECK (field IN ('front','example')), cache_key TEXT NOT NULL REFERENCES audio(cache_key),
  PRIMARY KEY (card_id, field, cache_key));
CREATE TABLE usage (month TEXT NOT NULL, meter TEXT NOT NULL, amount INTEGER NOT NULL, PRIMARY KEY (month, meter));
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT, stats TEXT);
INSERT INTO schema_version VALUES (1);
