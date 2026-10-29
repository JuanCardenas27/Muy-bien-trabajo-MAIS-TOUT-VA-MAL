-- frances state dump v1
CREATE TABLE attachments (id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id),
  kind TEXT NOT NULL CHECK (kind IN ('drive_file','link','youtube','form')), external_id TEXT NOT NULL,
  title TEXT, url TEXT, mime_type TEXT, drive_version TEXT,
  blob_sha256 TEXT REFERENCES blobs(sha256), export_pdf_sha256 TEXT REFERENCES blobs(sha256),
  export_text_sha256 TEXT REFERENCES blobs(sha256),
  status TEXT NOT NULL CHECK (status IN ('pending','downloaded','reference','skipped_too_large','forbidden','not_found','error')),
  error TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, removed_at TEXT,
  UNIQUE (item_id, kind, external_id));
CREATE TABLE audio (cache_key TEXT PRIMARY KEY, text TEXT NOT NULL, text_norm TEXT NOT NULL,
  voice_id TEXT NOT NULL, family TEXT NOT NULL, family_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','done','failed','failed_qa')), engine_used TEXT,
  path TEXT, duration_ms INTEGER, qa_cer REAL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
  updated_at TEXT NOT NULL);
CREATE TABLE blobs (sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, mime_type TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE card_audio (card_id TEXT NOT NULL REFERENCES cards(id),
  field TEXT NOT NULL CHECK (field IN ('front','example')), cache_key TEXT NOT NULL REFERENCES audio(cache_key),
  PRIMARY KEY (card_id, field, cache_key));
CREATE TABLE card_sources (card_id TEXT NOT NULL REFERENCES cards(id), item_id TEXT NOT NULL REFERENCES items(id),
  PRIMARY KEY (card_id, item_id));
CREATE TABLE cards (id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('vocab','phrase','grammar','conjugation','drill')),
  front_fr TEXT NOT NULL, back_es TEXT NOT NULL, example_fr TEXT, example_es TEXT, notes TEXT,
  ipa TEXT, phonemes TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]',
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE courses (id TEXT PRIMARY KEY, name TEXT NOT NULL, section TEXT, state TEXT NOT NULL,
  alternate_link TEXT, update_time TEXT NOT NULL, included INTEGER NOT NULL DEFAULT 1, raw_json TEXT NOT NULL);
CREATE TABLE extractions (blob_sha256 TEXT NOT NULL REFERENCES blobs(sha256), extractor_version TEXT NOT NULL,
  method TEXT NOT NULL, lang TEXT NOT NULL, char_count INTEGER NOT NULL, path TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (blob_sha256, extractor_version));
CREATE TABLE generations (item_id TEXT PRIMARY KEY REFERENCES items(id), input_hash TEXT NOT NULL,
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE items (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
  kind TEXT NOT NULL CHECK (kind IN ('coursework','material','announcement')), classroom_id TEXT NOT NULL,
  topic_id TEXT, title TEXT, text TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, alternate_link TEXT,
  creation_time TEXT NOT NULL, update_time TEXT NOT NULL, due_at TEXT, content_hash TEXT NOT NULL,
  raw_json TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, deleted_at TEXT,
  UNIQUE (kind, classroom_id));
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT, stats TEXT);
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE sheets (item_id TEXT PRIMARY KEY REFERENCES items(id), json TEXT NOT NULL,
  generator TEXT NOT NULL, generator_version TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE topics (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
  name TEXT NOT NULL, update_time TEXT NOT NULL);
CREATE TABLE usage (month TEXT NOT NULL, meter TEXT NOT NULL, amount INTEGER NOT NULL, PRIMARY KEY (month, meter));
CREATE TABLE watermarks (course_id TEXT NOT NULL, stream TEXT NOT NULL, last_update_time TEXT NOT NULL,
  last_run_at TEXT NOT NULL, PRIMARY KEY (course_id, stream));
INSERT INTO attachments VALUES ('at_0f4d4e8cfc4bfd0f', 'mt_demo4', 'drive_file', 'demo-file-4', 'Exercices nasales.pdf', 'https://example.org/drive/demo-file-4', 'application/pdf', '1', NULL, NULL, NULL, 'forbidden', '403 sin permiso de descarga', 1, '2026-10-01T13:00:00.000000Z', NULL);
INSERT INTO attachments VALUES ('at_29ebb3ecaf461e51', 'mt_demo3', 'drive_file', 'demo-file-3', 'Tableau.png', 'https://example.org/drive/demo-file-3', 'image/png', '1', '{{img1}}', NULL, NULL, 'downloaded', NULL, 1, '2026-10-01T13:00:00.000000Z', NULL);
INSERT INTO attachments VALUES ('at_30c7354561507085', 'mt_demo1', 'drive_file', 'demo-file-1', 'Leçon 1 — Les salutations.pdf', 'https://example.org/drive/demo-file-1', 'application/pdf', '1', '{{pdf1}}', NULL, NULL, 'downloaded', NULL, 1, '2026-10-01T13:00:00.000000Z', NULL);
INSERT INTO attachments VALUES ('at_8948549182c82663', 'mt_demo2', 'drive_file', 'demo-file-2', 'Leçon 2 — Les nasales.pdf', 'https://example.org/drive/demo-file-2', 'application/pdf', '1', '{{pdf2}}', NULL, NULL, 'downloaded', NULL, 1, '2026-10-01T13:00:00.000000Z', NULL);
INSERT INTO attachments VALUES ('at_adb49bc6e65a9817', 'an_demo6', 'link', 'https://example.org/demo/examen-oral', 'Consignes de l''examen', 'https://example.org/demo/examen-oral', NULL, NULL, NULL, NULL, NULL, 'reference', NULL, 0, '2026-10-01T13:00:00.000000Z', NULL);
INSERT INTO audio VALUES ('demo02c4c86c1b9bbdb5b176c2ed4e8c', 'Bonjour', 'Bonjour', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo02c4c86c1b9bbdb5b176c2ed4e8c.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo09074b7deb4ac637e7090ae76fe7', 'Je m''appelle Léa.', 'Je m''appelle Léa.', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo09074b7deb4ac637e7090ae76fe7.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo3adce81a8c68406ff56a09413e3e', 'rouge', 'rouge', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo3adce81a8c68406ff56a09413e3e.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo43be17824bc17b23d889343f4881', 'Au revoir', 'Au revoir', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo43be17824bc17b23d889343f4881.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo4811b29fabed5e8162492fc7c6d8', 'l''été', 'l''été', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo4811b29fabed5e8162492fc7c6d8.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo4f781e01dab1dab71872d13de5c0', 'le pont', 'le pont', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo4f781e01dab1dab71872d13de5c0.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo508d692a889a78554a5f8631cb4c', 'Comment ça va ?', 'Comment ça va ?', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo508d692a889a78554a5f8631cb4c.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo56a7a9a29f5a02c23965ddd37f7f', 'Bonjour', 'Bonjour', 'fr-FR-EloiseNeural', 'ms-neural', '1', 'pending', NULL, NULL, NULL, NULL, 0, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo6343e87954f4b659cdcbfca11229', 'Au revoir', 'Au revoir', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo6343e87954f4b659cdcbfca11229.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo6caa9141f86931e3fbe1545e100e', 'rouge', 'rouge', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo6caa9141f86931e3fbe1545e100e.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo7d0e2d171d9cc4b4955c343e2917', 'l''été', 'l''été', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo7d0e2d171d9cc4b4955c343e2917.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo8171723c65a75e8309642e5c027f', 'le vin', 'le vin', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo8171723c65a75e8309642e5c027f.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo87e4703789469050fa2176f98511', 'le vent', 'le vent', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo87e4703789469050fa2176f98511.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demo9d442c8ab6be5891dfe77373ef1b', 'le vent', 'le vent', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demo9d442c8ab6be5891dfe77373ef1b.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demoa97af89e2410da531085bb70d184', 'Enchanté', 'Enchanté', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demoa97af89e2410da531085bb70d184.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demod4a400c69f658aa4c8fab94cd57d', 'le pont', 'le pont', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demod4a400c69f658aa4c8fab94cd57d.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demodc06894b0a2121059368bb8a3fe3', 'Bonjour', 'Bonjour', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demodc06894b0a2121059368bb8a3fe3.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demoe4df10d09a1d8d413182cfab9af1', 'Je m''appelle Léa.', 'Je m''appelle Léa.', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demoe4df10d09a1d8d413182cfab9af1.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demoeae79faeb97e3ea0af7a1e4ac99c', 'Comment ça va ?', 'Comment ça va ?', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demoeae79faeb97e3ea0af7a1e4ac99c.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demof13cb03e2b2ff0f72a9ca6a8e810', 'Enchanté', 'Enchanté', 'fr-FR-HenriNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demof13cb03e2b2ff0f72a9ca6a8e810.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO audio VALUES ('demofdc66bd5d756c122479c612667ac', 'le vin', 'le vin', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done', 'espeak-ng', 'audio/demofdc66bd5d756c122479c612667ac.mp3', NULL, NULL, 1, NULL, '2026-10-14T10:17:00.000000Z');
INSERT INTO blobs VALUES ('{{pdf2}}', {{pdf2_size}}, 'application/pdf', '2026-10-01T13:00:00.000000Z');
INSERT INTO blobs VALUES ('{{img1}}', {{img1_size}}, 'image/png', '2026-10-01T13:00:00.000000Z');
INSERT INTO blobs VALUES ('{{pdf1}}', {{pdf1_size}}, 'application/pdf', '2026-10-01T13:00:00.000000Z');
INSERT INTO card_audio VALUES ('c_021288c7b84fd40a', 'front', 'demoa97af89e2410da531085bb70d184');
INSERT INTO card_audio VALUES ('c_021288c7b84fd40a', 'front', 'demof13cb03e2b2ff0f72a9ca6a8e810');
INSERT INTO card_audio VALUES ('c_51285ec809c6bcbd', 'front', 'demo87e4703789469050fa2176f98511');
INSERT INTO card_audio VALUES ('c_51285ec809c6bcbd', 'front', 'demo9d442c8ab6be5891dfe77373ef1b');
INSERT INTO card_audio VALUES ('c_6e35c77c9ee5eaa4', 'front', 'demo4811b29fabed5e8162492fc7c6d8');
INSERT INTO card_audio VALUES ('c_6e35c77c9ee5eaa4', 'front', 'demo7d0e2d171d9cc4b4955c343e2917');
INSERT INTO card_audio VALUES ('c_7a8d3659b0d74a26', 'front', 'demo508d692a889a78554a5f8631cb4c');
INSERT INTO card_audio VALUES ('c_7a8d3659b0d74a26', 'front', 'demoeae79faeb97e3ea0af7a1e4ac99c');
INSERT INTO card_audio VALUES ('c_89399c4d8d8f668e', 'front', 'demo43be17824bc17b23d889343f4881');
INSERT INTO card_audio VALUES ('c_89399c4d8d8f668e', 'front', 'demo6343e87954f4b659cdcbfca11229');
INSERT INTO card_audio VALUES ('c_9651d8be5e2de441', 'front', 'demo8171723c65a75e8309642e5c027f');
INSERT INTO card_audio VALUES ('c_9651d8be5e2de441', 'front', 'demofdc66bd5d756c122479c612667ac');
INSERT INTO card_audio VALUES ('c_a4898c19b6e8b6b5', 'front', 'demo4f781e01dab1dab71872d13de5c0');
INSERT INTO card_audio VALUES ('c_a4898c19b6e8b6b5', 'front', 'demod4a400c69f658aa4c8fab94cd57d');
INSERT INTO card_audio VALUES ('c_b71a7f8e37dd144e', 'front', 'demo3adce81a8c68406ff56a09413e3e');
INSERT INTO card_audio VALUES ('c_b71a7f8e37dd144e', 'front', 'demo6caa9141f86931e3fbe1545e100e');
INSERT INTO card_audio VALUES ('c_c75b86b7b465b7a3', 'front', 'demo09074b7deb4ac637e7090ae76fe7');
INSERT INTO card_audio VALUES ('c_c75b86b7b465b7a3', 'front', 'demoe4df10d09a1d8d413182cfab9af1');
INSERT INTO card_audio VALUES ('c_fc43341b9ea63489', 'front', 'demo02c4c86c1b9bbdb5b176c2ed4e8c');
INSERT INTO card_audio VALUES ('c_fc43341b9ea63489', 'front', 'demo56a7a9a29f5a02c23965ddd37f7f');
INSERT INTO card_audio VALUES ('c_fc43341b9ea63489', 'front', 'demodc06894b0a2121059368bb8a3fe3');
INSERT INTO card_sources VALUES ('c_021288c7b84fd40a', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_103f40954b6a42c7', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_21e0214a1451ec55', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_255ab15c84b5e5b6', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_29897bbc8ca95f83', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_2b2bed3539b64aa4', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_2f9fcc08e4f07f79', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_308aa85e944e0e11', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_329f4d78c7ac86a5', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_3af00f3f92f08d63', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_3d23a60e34e6422b', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_51285ec809c6bcbd', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_61e7721dd0aa5e70', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_6aabe6d96f73dbc8', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_6e35c77c9ee5eaa4', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_7a8d3659b0d74a26', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_7d8e3f73cce96ae7', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_83a33570e3cf3352', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_89399c4d8d8f668e', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_9651d8be5e2de441', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_9b1fd5db1a2868b1', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_a4898c19b6e8b6b5', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_ab3b817df3a4716e', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_b71a7f8e37dd144e', 'mt_demo2');
INSERT INTO card_sources VALUES ('c_b940f4889b6ac49a', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_c75b86b7b465b7a3', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_ceb219ee188c8af0', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_e62e8ed8d351151d', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_e67dc109f6a46a84', 'mt_demo1');
INSERT INTO card_sources VALUES ('c_fc43341b9ea63489', 'mt_demo1');
INSERT INTO cards VALUES ('c_021288c7b84fd40a', 'vocab', 'Enchanté', 'Encantado', 'Enchanté, je suis Paul.', 'Encantado, soy Paul.', 'Femenino: enchantée.', 'v1|ɑ̃ʃɑ̃tˈe', '["ɑ̃", "ʃ", "t", "e"]', '["presentación"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_103f40954b6a42c7', 'drill', 'la maison', 'la casa', NULL, NULL, NULL, 'v1|la- mɛzˈɔ̃', '["l", "a", "m", "ɛ", "z", "ɔ̃"]', '["taladro", "on"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_21e0214a1451ec55', 'phrase', 'À bientôt', 'Hasta pronto', NULL, NULL, NULL, 'v1|a bjɛ̃tˈoː', '["a", "b", "j", "ɛ̃", "t", "o"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_255ab15c84b5e5b6', 'drill', 'la fête', 'la fiesta', NULL, NULL, 'fée / fête', 'v1|la- fˈɛt', '["l", "a", "f", "ɛ", "t"]', '["taladro", "e_vs_ɛ"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_29897bbc8ca95f83', 'phrase', 'S''il vous plaît', 'Por favor (formal)', NULL, NULL, NULL, 'v1|sil vu plˈɛ', '["s", "i", "l", "v", "u", "p", "ɛ"]', '["cortesía"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_2b2bed3539b64aa4', 'drill', 'le pain', 'el pan', NULL, NULL, 'pain / pont / pan', 'v1|lə- pˈɛ̃', '["l", "ə", "p", "ɛ̃"]', '["taladro", "in"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_2f9fcc08e4f07f79', 'phrase', 'Merci beaucoup', 'Muchas gracias', NULL, NULL, NULL, 'v1|mɛʁsˈi bokˈu', '["m", "ɛ", "ʁ", "s", "i", "b", "o", "k", "u"]', '["cortesía"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_308aa85e944e0e11', 'phrase', 'Un bon vin blanc.', 'Un buen vino blanco.', NULL, NULL, 'Frase clásica con tres nasales.', 'v1|œ̃ bˈɔ̃ vˈɛ̃ blˈɑ̃', '["œ̃", "b", "ɔ̃", "v", "ɛ̃", "l", "ɑ̃"]', '["nasal"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_329f4d78c7ac86a5', 'vocab', 'Bonsoir', 'Buenas noches (al llegar)', 'Bonsoir, tout le monde.', 'Buenas noches a todos.', NULL, 'v1|bɔ̃swˈaʁ', '["b", "ɔ̃", "s", "w", "a", "ʁ"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_3af00f3f92f08d63', 'drill', 'merci', 'gracias', NULL, NULL, NULL, 'v1|mɛʁsˈi', '["m", "ɛ", "ʁ", "s", "i"]', '["taladro", "r"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_3d23a60e34e6422b', 'vocab', 'Salut', 'Hola (informal)', 'Salut, ça va ?', 'Hola, ¿qué tal?', 'Solo con amigos.', 'v1|salˈy', '["s", "a", "l", "y"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_51285ec809c6bcbd', 'drill', 'le vent', 'el viento', NULL, NULL, 'vent / vont / vin', 'v1|lə- vˈɑ̃', '["l", "ə", "v", "ɑ̃"]', '["taladro", "an"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_61e7721dd0aa5e70', 'vocab', 'le chien', 'el perro', NULL, NULL, NULL, 'v1|lə- ʃjˈɛ̃', '["l", "ə", "ʃ", "j", "ɛ̃"]', '["nasal"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_6aabe6d96f73dbc8', 'vocab', 'le prénom', 'el nombre (de pila)', 'Quel est ton prénom ?', '¿Cuál es tu nombre?', NULL, 'v1|lə- pʁenˈɔ̃', '["l", "ə", "p", "ʁ", "e", "n", "ɔ̃"]', '["presentación"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_6e35c77c9ee5eaa4', 'drill', 'l''été', 'el verano', NULL, NULL, 'été / était', 'v1|letˈe', '["l", "e", "t"]', '["taladro", "e_vs_ɛ"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_7a8d3659b0d74a26', 'phrase', 'Comment ça va ?', '¿Cómo estás?', NULL, NULL, NULL, 'v1|kɔmˌɑ̃ sa vˈa', '["k", "ɔ", "m", "ɑ̃", "s", "a", "v"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_7d8e3f73cce96ae7', 'vocab', 'le pantalon', 'el pantalón', NULL, NULL, NULL, 'v1|lə- pɑ̃talˈɔ̃', '["l", "ə", "p", "ɑ̃", "t", "a", "ɔ̃"]', '["nasal"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_83a33570e3cf3352', 'vocab', 'lundi', 'lunes', NULL, NULL, NULL, 'v1|lœ̃dˈi', '["l", "œ̃", "d", "i"]', '["calendario"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_89399c4d8d8f668e', 'phrase', 'Au revoir', 'Adiós', NULL, NULL, NULL, 'v1|o ʁəvwˈaʁ', '["o", "ʁ", "ə", "v", "w", "a"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_9651d8be5e2de441', 'drill', 'le vin', 'el vino', NULL, NULL, 'vin / vent / vont', 'v1|lə- vˈɛ̃', '["l", "ə", "v", "ɛ̃"]', '["taladro", "in"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_9b1fd5db1a2868b1', 'drill', 'dans', 'en; dentro', NULL, NULL, NULL, 'v1|dˈɑ̃', '["d", "ɑ̃"]', '["taladro", "an"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_a4898c19b6e8b6b5', 'drill', 'le pont', 'el puente', NULL, NULL, 'pont / pan / pain', 'v1|lə- pˈɔ̃', '["l", "ə", "p", "ɔ̃"]', '["taladro", "on"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_ab3b817df3a4716e', 'vocab', 'le restaurant', 'el restaurante', NULL, NULL, NULL, 'v1|lə- ʁɛstoʁˈɑ̃', '["l", "ə", "ʁ", "ɛ", "s", "t", "o", "ɑ̃"]', '["nasal"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_b71a7f8e37dd144e', 'drill', 'rouge', 'rojo', NULL, NULL, 'rouge / bouge', 'v1|ʁˈuʒ', '["ʁ", "u", "ʒ"]', '["taladro", "r"]', 'seed', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_b940f4889b6ac49a', 'conjugation', 'être', 'ser; estar', 'Je suis étudiant.', 'Soy estudiante.', 'je suis, tu es, il est, nous sommes, vous êtes, ils sont', 'v1|ˈɛtʁ', '["ɛ", "t", "ʁ"]', '["verbo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_c75b86b7b465b7a3', 'phrase', 'Je m''appelle Léa.', 'Me llamo Léa.', NULL, NULL, NULL, 'v1|ʒə- mapˈɛl leˈa', '["ʒ", "ə", "m", "a", "p", "ɛ", "l", "e"]', '["presentación"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_ceb219ee188c8af0', 'conjugation', 's''appeler', 'llamarse', 'Il s''appelle Marc.', 'Se llama Marc.', 'je m''appelle, tu t''appelles, il s''appelle', 'v1|saplˈe', '["s", "a", "p", "l", "e"]', '["verbo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_e62e8ed8d351151d', 'grammar', 'tu / vous', 'tú / usted', 'Vous êtes madame Martin ?', '¿Usted es la señora Martin?', '«vous» es formal o plural.', 'v1|ty vˈu', '["t", "y", "v", "u"]', '["gramática"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_e67dc109f6a46a84', 'phrase', 'Excusez-moi', 'Disculpe', NULL, NULL, NULL, 'v1|ɛkskyzˈemwˈa', '["ɛ", "k", "s", "y", "z", "e", "m", "w", "a"]', '["cortesía"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO cards VALUES ('c_fc43341b9ea63489', 'phrase', 'Bonjour', 'Buenos días; hola', 'Bonjour, madame !', '¡Buenos días, señora!', NULL, 'v1|bɔ̃ʒˈuʁ', '["b", "ɔ̃", "ʒ", "u", "ʁ"]', '["saludo"]', 'demo', '1', 0, '2026-10-14T10:17:00.000000Z', '2026-10-14T10:17:00.000000Z');
INSERT INTO courses VALUES ('demo-course', 'Français A2 – Démo', 'Groupe démo', 'ACTIVE', 'https://example.org/classroom/demo-course', '2026-10-01T13:00:00.000000Z', 1, '{}');
INSERT INTO items VALUES ('an_demo6', 'demo-course', 'announcement', 'demo6', 'demo-topic-3', 'Annonce : examen oral', 'El examen oral será el viernes 24 de octubre. Preparen la presentación personal y repasen las vocales nasales.', 'PUBLISHED', 'https://example.org/classroom/demo6', '2026-10-12T13:00:00.000000Z', '2026-10-12T13:00:00.000000Z', NULL, '632c237cbfcda9d22eea184acb041677e2b127087a5da031e38e2efc94b5b50a', '{}', '2026-10-12T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO items VALUES ('cw_demo5', 'demo-course', 'coursework', 'demo5', 'demo-topic-1', 'Devoir : se présenter', 'Enregistrez une courte présentation : votre prénom, votre âge et votre ville.', 'PUBLISHED', 'https://example.org/classroom/demo5', '2026-10-10T13:00:00.000000Z', '2026-10-10T13:00:00.000000Z', '2026-10-20T04:59:00.000000Z', '6857890e122cff4d24462441a56d03e1925d295e53d144db9d6acea8141d259d', '{}', '2026-10-10T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO items VALUES ('mt_demo1', 'demo-course', 'material', 'demo1', 'demo-topic-1', 'Leçon 1 — Les salutations', 'Bonjour à tous ! Aujourd''hui, nous apprenons à saluer et à nous présenter. Lisez le document et répétez les phrases à voix haute.', 'PUBLISHED', 'https://example.org/classroom/demo1', '2026-10-01T13:00:00.000000Z', '2026-10-01T13:00:00.000000Z', NULL, '43dbd805aa9f016a2d014eeda44be3608c03b08a1f58daac00d351128948164c', '{}', '2026-10-01T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO items VALUES ('mt_demo2', 'demo-course', 'material', 'demo2', 'demo-topic-2', 'Leçon 2 — Les nasales', 'Les voyelles nasales du français : an, on, in. Écoutez bien la différence entre le vent, le vin et le pont.', 'PUBLISHED', 'https://example.org/classroom/demo2', '2026-10-06T13:00:00.000000Z', '2026-10-06T13:00:00.000000Z', NULL, 'dd0d7079f39d6daae5df02a5a4dcf3e222fd817368a1251812f068e94f3cb505', '{}', '2026-10-06T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO items VALUES ('mt_demo3', 'demo-course', 'material', 'demo3', 'demo-topic-1', 'Le tableau du jour', 'Voici la photo du tableau de la classe d''aujourd''hui.', 'PUBLISHED', 'https://example.org/classroom/demo3', '2026-10-08T13:00:00.000000Z', '2026-10-08T13:00:00.000000Z', NULL, '472d50d43aea4e183de0ba3bcb91bda1129a1fe1f7ca506ef6f3f897a26d3e9d', '{}', '2026-10-08T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO items VALUES ('mt_demo4', 'demo-course', 'material', 'demo4', 'demo-topic-2', 'Document protégé', 'Exercices supplémentaires sur les nasales.', 'PUBLISHED', 'https://example.org/classroom/demo4', '2026-10-09T13:00:00.000000Z', '2026-10-09T13:00:00.000000Z', NULL, 'fcde969ff76aba692f5443f4016ec908f71f75c90f1bfd1850913c880f6dcc86', '{}', '2026-10-09T13:00:00.000000Z', '2026-10-14T10:17:00.000000Z', NULL);
INSERT INTO schema_version VALUES (1);
INSERT INTO sheets VALUES ('mt_demo1', '{"grammar": [{"examples": [{"es": "¿Cómo te llamas?", "fr": "Tu t''appelles comment ?"}, {"es": "¿Cómo se llama usted?", "fr": "Comment vous appelez-vous ?"}], "explanation_es": "«tu» se usa con amigos y familia; «vous» es formal o plural.", "title": "Tu ou vous ?"}], "key_phrases": [{"es": "Me llamo Léa.", "fr": "Je m''appelle Léa."}, {"es": "¿Cómo estás?", "fr": "Comment ça va ?"}], "summary_es": "Saludos formales e informales y cómo presentarse en francés.", "vocab_card_ids": ["c_fc43341b9ea63489", "c_329f4d78c7ac86a5", "c_3d23a60e34e6422b", "c_021288c7b84fd40a", "c_6aabe6d96f73dbc8"]}', 'demo', '1', '2026-10-14T10:17:00.000000Z');
INSERT INTO sheets VALUES ('mt_demo2', '{"grammar": [{"examples": [{"es": "el viento", "fr": "le vent"}, {"es": "el vino", "fr": "le vin"}, {"es": "el puente", "fr": "le pont"}], "explanation_es": "La vocal se pronuncia dejando pasar aire por la nariz; la n no suena.", "title": "Les voyelles nasales"}], "key_phrases": [{"es": "Un buen vino blanco.", "fr": "Un bon vin blanc."}], "summary_es": "Las tres vocales nasales del francés: /ɑ̃/, /ɔ̃/ y /ɛ̃/.", "vocab_card_ids": ["c_ab3b817df3a4716e", "c_7d8e3f73cce96ae7", "c_61e7721dd0aa5e70", "c_83a33570e3cf3352"]}', 'demo', '1', '2026-10-14T10:17:00.000000Z');
INSERT INTO topics VALUES ('demo-topic-1', 'demo-course', 'Salutations', '2026-10-01T13:00:00.000000Z');
INSERT INTO topics VALUES ('demo-topic-2', 'demo-course', 'Les nasales', '2026-10-01T13:00:00.000000Z');
INSERT INTO topics VALUES ('demo-topic-3', 'demo-course', 'Annonces', '2026-10-01T13:00:00.000000Z');
