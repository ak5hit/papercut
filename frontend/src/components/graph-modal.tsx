"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import { GraphView } from "./graph-view";

interface GraphModalProps {
  documentId: string | null;
  documentName?: string;
  onClose: () => void;
}

export function GraphModal({ documentId, documentName, onClose }: GraphModalProps) {
  useEffect(() => {
    if (!documentId) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [documentId, onClose]);

  if (!documentId) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 transition-opacity"
      onClick={onClose}
    >
      <div
        className="relative w-[80vw] h-[80vh] max-w-7xl rounded-xl border bg-background shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
          <h2 className="text-sm font-semibold truncate">
            {documentName || "Knowledge Graph"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
        <div className="flex-1 p-4 overflow-hidden">
          <GraphView
            documentId={documentId}
            documentName={documentName}
            containerClassName="h-full"
          />
        </div>
      </div>
    </div>
  );
}
