"use client";

import { useState, useCallback, useRef } from "react";
import { Upload, Loader2, FileText } from "lucide-react";

interface UploadDropzoneProps {
  onUpload: (file: File, documentType: string) => void;
  uploading: boolean;
  disabled?: boolean;
}

const DOCUMENT_TYPES = [
  { value: "", label: "Auto-detect" },
  { value: "resume", label: "Resume / CV" },
] as const;

export function UploadDropzone({
  onUpload,
  uploading,
  disabled = false,
}: UploadDropzoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const triggerUpload = useCallback(() => {
    if (selectedFile && !uploading && !disabled) {
      onUpload(selectedFile, documentType);
    }
  }, [selectedFile, documentType, uploading, disabled, onUpload]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (disabled || uploading) return;
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") {
        setSelectedFile(file);
      }
    },
    [disabled, uploading]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setSelectedFile(file);
      }
    },
    []
  );

  const handleSelectNew = useCallback(() => {
    if (uploading || disabled) return;
    setSelectedFile(null);
    setDocumentType("");
    fileInputRef.current?.click();
  }, [uploading, disabled]);

  return (
    <div className="space-y-3">
      {!selectedFile ? (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => {
            if (!disabled && !uploading) {
              fileInputRef.current?.click();
            }
          }}
          className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors bg-gray-50 ${
            disabled || uploading
              ? "border-gray-200 cursor-not-allowed opacity-60"
              : "border-gray-300 hover:border-blue-500 cursor-pointer"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleChange}
            disabled={disabled || uploading}
            className="hidden"
          />
          <Upload className="mx-auto h-10 w-10 text-gray-400 mb-3" />
          <p className="text-sm text-gray-600">
            {disabled
              ? "Please wait — system is still initializing..."
              : uploading
              ? "Uploading..."
              : "Drop a PDF here, or click to browse"}
          </p>
        </div>
      ) : (
        <div className="border rounded-lg p-4 bg-white shadow-sm space-y-3">
          <div className="flex items-center gap-3">
            <FileText className="h-8 w-8 text-blue-500 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-gray-900 truncate">
                {selectedFile.name}
              </p>
              <p className="text-xs text-gray-500">
                {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
              </p>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Document Type
            </label>
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              disabled={disabled || uploading}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {DOCUMENT_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={triggerUpload}
              disabled={uploading || disabled}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : disabled ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Initializing...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Upload
                </>
              )}
            </button>
            <button
              onClick={handleSelectNew}
              disabled={uploading || disabled}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Change
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
