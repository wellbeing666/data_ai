interface InsightRendererProps {
  content: string;
  isHtml?: boolean;
}

export function InsightRenderer({ content, isHtml = false }: InsightRendererProps) {
  return (
    <div className="insight-renderer-container">
      {isHtml ? (
        <div dangerouslySetInnerHTML={{ __html: content }} />
      ) : (
        <div className="markdown-body">{content}</div>
      )}
    </div>
  );
}
