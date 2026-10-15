/* GENERADO — no editar. Fuente: contracts/*.schema.json (npm run gen:types) */

export type Id = string;
export type Mime = string;
export type Sha256 = string;
export type Size = number;
export type Id1 = string;
export type ItemId = string;
export type Kind = 'drive_file' | 'link' | 'youtube' | 'form';
export type MimeType = string | null;
export type Status =
  | 'pending'
  | 'downloaded'
  | 'reference'
  | 'skipped_too_large'
  | 'forbidden'
  | 'not_found'
  | 'error';
export type Title = string | null;
export type Url = string | null;
export type Attachments = AttachmentOut[];
export type Field = 'front' | 'example';
export type VoiceId = string;
export type Audio = AudioRef[];
export type Field1 = 'front' | 'example';
export type VoiceId1 = string;
export type AudioPending = AudioPending1[];
export type BackEs = string;
export type ExampleEs = string | null;
export type ExampleFr = string | null;
export type FrontFr = string;
export type Id2 = string;
export type Ipa = string | null;
export type Kind1 = 'vocab' | 'phrase' | 'grammar' | 'conjugation' | 'drill';
export type Notes = string | null;
export type Phonemes = string[];
export type SourceItemIds = string[];
export type Stale = boolean;
export type Tags = string[];
export type Cards = CardOut[];
export type Id3 = string;
export type Name = string;
export type Section = string | null;
export type Courses = CourseOut[];
export type CardIds = string[];
export type Curated = boolean;
export type Id4 = string;
export type Phoneme = string;
export type TitleEs = string;
export type Drills = DrillDeck[];
export type GeneratedAt = string;
export type AlternateLink = string | null;
export type AttachmentIds = string[];
export type CardIds1 = string[];
export type CourseId = string;
export type CreatedAt = string;
export type DueAt = string | null;
export type FirstSeenAt = string;
export type HasSheet = boolean;
export type Id5 = string;
export type Kind2 = 'coursework' | 'material' | 'announcement';
export type Text = string;
export type TextLang = 'fr' | 'es' | 'en' | 'mixed' | 'unknown';
export type Title1 = string | null;
export type TopicId = string | null;
export type UpdatedAt = string;
export type Items = ItemOut[];
export type SchemaVersion = 1;
export type Es = string;
export type Fr = string;
export type Examples = Example[];
export type ExplanationEs = string;
export type Title2 = string;
export type Grammar = GrammarPoint[];
export type ItemId1 = string;
export type KeyPhrases = Example[];
export type SummaryEs = string;
export type VocabCardIds = string[];
export type Sheets = StudySheet[];
export type Key = string;
export type Locale = 'fr-FR';
export type Region = string;
export type CourseId1 = string;
export type Id6 = string;
export type Name1 = string;
export type Topics = TopicOut[];
export type Accent = string;
export type Age = 'adult' | 'teen' | 'child';
export type Gender = 'female' | 'male';
export type Id7 = string;
export type Label = string;
export type Voices = VoiceOut[];
export type Check = string;
export type CreatedAt1 = string;
export type Format = 'FRB1';
export type Hash = 'SHA-256';
export type Iterations = number;
export type Name2 = 'PBKDF2';
export type Salt = string;
export type At = string;
export type CardId = string | null;
export type DurationMs = number;
export type Id8 = string;
export type RecognizedText = string;
export type ReferenceText = string;
export type Accuracy = number;
export type Completeness = number;
export type Fluency = number;
export type Pron = number;
export type Accuracy1 = number;
export type ErrorType =
  | 'None'
  | 'Omission'
  | 'Insertion'
  | 'Mispronunciation'
  | 'UnexpectedBreak'
  | 'MissingBreak'
  | 'Monotone';
export type Accuracy2 = number;
export type Phoneme1 = string;
export type Phonemes1 = PhonemeScore[];
export type Word = string;
export type Words = WordScore[];

export interface FrancesContracts {
  content_index?: ContentIndex;
  bundle_manifest?: BundleManifest;
  pron_result?: PronResult;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "ContentIndex".
 */
export interface ContentIndex {
  attachments: Attachments;
  cards: Cards;
  courses: Courses;
  drills: Drills;
  generated_at: GeneratedAt;
  items: Items;
  schema_version: SchemaVersion;
  sheets: Sheets;
  speech: SpeechCredentials | null;
  topics: Topics;
  voices: Voices;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "AttachmentOut".
 */
export interface AttachmentOut {
  file: FileRef | null;
  id: Id1;
  item_id: ItemId;
  kind: Kind;
  mime_type: MimeType;
  status: Status;
  title: Title;
  url: Url;
  view_pdf: FileRef | null;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "FileRef".
 */
export interface FileRef {
  id: Id;
  mime: Mime;
  sha256: Sha256;
  size: Size;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "CardOut".
 */
export interface CardOut {
  audio: Audio;
  audio_pending: AudioPending;
  back_es: BackEs;
  example_es: ExampleEs;
  example_fr: ExampleFr;
  front_fr: FrontFr;
  id: Id2;
  ipa: Ipa;
  kind: Kind1;
  notes: Notes;
  phonemes: Phonemes;
  source_item_ids: SourceItemIds;
  stale: Stale;
  tags: Tags;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "AudioRef".
 */
export interface AudioRef {
  field: Field;
  file: FileRef;
  voice_id: VoiceId;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "AudioPending".
 */
export interface AudioPending1 {
  field: Field1;
  voice_id: VoiceId1;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "CourseOut".
 */
export interface CourseOut {
  id: Id3;
  name: Name;
  section: Section;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "DrillDeck".
 */
export interface DrillDeck {
  card_ids: CardIds;
  curated: Curated;
  id: Id4;
  phoneme: Phoneme;
  title_es: TitleEs;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "ItemOut".
 */
export interface ItemOut {
  alternate_link: AlternateLink;
  attachment_ids: AttachmentIds;
  card_ids: CardIds1;
  course_id: CourseId;
  created_at: CreatedAt;
  due_at: DueAt;
  first_seen_at: FirstSeenAt;
  has_sheet: HasSheet;
  id: Id5;
  kind: Kind2;
  text: Text;
  text_lang: TextLang;
  title: Title1;
  topic_id: TopicId;
  updated_at: UpdatedAt;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "StudySheet".
 */
export interface StudySheet {
  grammar: Grammar;
  item_id: ItemId1;
  key_phrases: KeyPhrases;
  summary_es: SummaryEs;
  vocab_card_ids: VocabCardIds;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "GrammarPoint".
 */
export interface GrammarPoint {
  examples: Examples;
  explanation_es: ExplanationEs;
  title: Title2;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "Example".
 */
export interface Example {
  es: Es;
  fr: Fr;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "SpeechCredentials".
 */
export interface SpeechCredentials {
  key: Key;
  locale?: Locale;
  region: Region;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "TopicOut".
 */
export interface TopicOut {
  course_id: CourseId1;
  id: Id6;
  name: Name1;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "VoiceOut".
 */
export interface VoiceOut {
  accent: Accent;
  age: Age;
  gender: Gender;
  id: Id7;
  label: Label;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "BundleManifest".
 */
export interface BundleManifest {
  check: Check;
  created_at: CreatedAt1;
  format: Format;
  index: FileRef;
  kdf: KdfParams;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "KdfParams".
 */
export interface KdfParams {
  hash: Hash;
  iterations: Iterations;
  name: Name2;
  salt: Salt;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "PronResult".
 */
export interface PronResult {
  at: At;
  card_id: CardId;
  duration_ms: DurationMs;
  id: Id8;
  recognized_text: RecognizedText;
  reference_text: ReferenceText;
  scores: PronScores;
  words: Words;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "PronScores".
 */
export interface PronScores {
  accuracy: Accuracy;
  completeness: Completeness;
  fluency: Fluency;
  pron: Pron;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "WordScore".
 */
export interface WordScore {
  accuracy: Accuracy1;
  error_type: ErrorType;
  phonemes: Phonemes1;
  word: Word;
}
/**
 * This interface was referenced by `FrancesContracts`'s JSON-Schema
 * via the `definition` "PhonemeScore".
 */
export interface PhonemeScore {
  accuracy: Accuracy2;
  phoneme: Phoneme1;
}
