// Detalle de publicación (Task WEB-06): título, metadatos, texto con enlaces
// seguros (nunca `innerHTML`), adjuntos con visores PDF/imagen y enlace a la
// ficha. El texto lleva `lang="fr"` solo si `text_lang === "fr"` (R-19).

import type { JSX, ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import type { AttachmentOut, FileRef, ItemOut } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { formatLong } from '../i18n/dates';
import { t } from '../i18n/es';
import type { EsKey } from '../i18n/es';
import { ImageViewer } from '../ui/viewers/ImageViewer';
import { PdfViewer } from '../ui/viewers/PdfViewer';

const URL_RE = /https?:\/\/[^\s<>"]+/g;

function TextWithLinks({ text }: { text: string }): JSX.Element {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(URL_RE)) {
    const index = match.index ?? 0;
    if (index > last) {
      nodes.push(text.slice(last, index));
    }
    const url = match[0];
    nodes.push(
      <a key={index} href={url} target="_blank" rel="noopener noreferrer">
        {url}
      </a>,
    );
    last = index + url.length;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return <>{nodes}</>;
}

const LINK_LABELS: Record<'link' | 'youtube' | 'form', EsKey> = {
  link: 'att.link',
  youtube: 'att.youtube',
  form: 'att.form',
};

function AttachmentView({
  attachment,
  itemTitle,
}: {
  attachment: AttachmentOut;
  itemTitle: string;
}): JSX.Element {
  const pdf: FileRef | null =
    attachment.file !== null && attachment.file.mime === 'application/pdf'
      ? attachment.file
      : attachment.view_pdf;
  if (pdf !== null) {
    return <PdfViewer file={pdf} title={attachment.title ?? itemTitle} />;
  }
  const file = attachment.file;
  if (file !== null && file.mime.startsWith('image/')) {
    return <ImageViewer file={file} alt={attachment.title ?? itemTitle} />;
  }
  if (
    (attachment.kind === 'link' ||
      attachment.kind === 'youtube' ||
      attachment.kind === 'form') &&
    attachment.url !== null
  ) {
    return (
      <a
        href={attachment.url}
        target="_blank"
        rel="noopener noreferrer"
        className="attachment-link"
      >
        {t(LINK_LABELS[attachment.kind])}
      </a>
    );
  }
  return <p>{t('att.unavailable')}</p>;
}

export default function ItemDetail(): JSX.Element {
  const { index } = useContent();
  const { id } = useParams();
  const item: ItemOut | undefined = index.items.find((it) => it.id === id);
  if (item === undefined) {
    return <p>{t('item.notFound')}</p>;
  }
  const title = item.title ?? t('item.untitled');
  const attachments = item.attachment_ids
    .map((attachmentId) =>
      index.attachments.find((att) => att.id === attachmentId),
    )
    .filter((att): att is AttachmentOut => att !== undefined);

  return (
    <article>
      <h1>{title}</h1>
      <p>{t('item.created', { date: formatLong(item.created_at) })}</p>
      <p>{t('item.updated', { date: formatLong(item.updated_at) })}</p>
      {item.due_at !== null && (
        <p>{t('item.due', { date: formatLong(item.due_at) })}</p>
      )}
      {item.alternate_link !== null && (
        <a href={item.alternate_link} target="_blank" rel="noopener noreferrer">
          {t('item.openClassroom')}
        </a>
      )}
      {item.has_sheet && (
        <p>
          <Link to={`/item/${item.id}/sheet`}>{t('item.sheet')}</Link>
        </p>
      )}
      <div {...(item.text_lang === 'fr' ? { lang: 'fr' } : {})}>
        <TextWithLinks text={item.text} />
      </div>
      {attachments.length > 0 && (
        <ul className="attachments">
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              {attachment.title !== null && <h2>{attachment.title}</h2>}
              <AttachmentView attachment={attachment} itemTitle={title} />
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
