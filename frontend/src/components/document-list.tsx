import type { Document } from "@/lib/types";

interface DocumentListProps {
  documents: Document[];
}

export function DocumentList({ documents }: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="text-gray-500 text-sm">No documents uploaded yet.</p>;
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="flex items-center justify-between p-3 bg-white border rounded-lg shadow-sm"
        >
          <div className="min-w-0">
            <p className="font-medium truncate">{doc.filename}</p>
            <p className="text-xs text-gray-500">
              {doc.page_count} pages · {doc.extraction_strategy} ·{" "}
              <span
                className={
                  doc.embedding_status === "completed"
                    ? "text-green-600"
                    : doc.embedding_status === "failed"
                    ? "text-red-600"
                    : "text-yellow-600"
                }
              >
                {doc.embedding_status}
              </span>
            </p>
          </div>
          <span className="text-xs text-gray-400 shrink-0 ml-4">
            {new Date(doc.created_at).toLocaleDateString()}
          </span>
        </div>
      ))}
    </div>
  );
}
