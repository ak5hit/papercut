import type { Document } from "@/lib/types";
import { Trash2 } from "lucide-react";

interface DocumentListProps {
  documents: Document[];
  onDelete?: (id: string) => void;
}

export function DocumentList({ documents, onDelete }: DocumentListProps) {
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
          <div className="min-w-0 flex-1">
            <p className="font-medium truncate">{doc.filename}</p>
            <p className="text-xs text-gray-500">
              {doc.page_count} pages · {doc.extraction_strategy}
              {doc.document_type && ` · ${doc.document_type}`}
              ·{" "}
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
          <div className="flex items-center gap-3 shrink-0 ml-4">
            <span className="text-xs text-gray-400">
              {new Date(doc.created_at).toLocaleDateString()}
            </span>
            {onDelete && (
              <button
                onClick={() => onDelete(doc.id)}
                className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                title="Delete document"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
