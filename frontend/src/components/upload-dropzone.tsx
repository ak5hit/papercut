"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Upload, Loader2, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { checkDuplicate } from "@/lib/api-client";

interface UploadDropzoneProps {
  onUpload: (file: File) => void;
  uploading: boolean;
  disabled?: boolean;
  docResult?: Record<string, unknown> | null;
  uploadError?: string | null;
}

export function UploadDropzone({
  onUpload,
  uploading,
  disabled = false,
  docResult,
  uploadError,
}: UploadDropzoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (docResult || uploadError) {
      setSelectedFile(null);
      setDuplicateError(null);
    }
  }, [docResult, uploadError]);

  const handleFileSelect = useCallback(async (file: File) => {
    setSelectedFile(file);
    setDuplicateError(null);

    try {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
      const contentHash = Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");

      const result = await checkDuplicate(contentHash);
      if (result.is_duplicate) {
        setDuplicateError(
          `This document was already uploaded as "${result.existing_filename}"`,
        );
      }
    } catch {
      // Network error — backend enforces duplicate check on upload
    }
  }, []);

  const triggerUpload = useCallback(() => {
    if (selectedFile && !uploading && !disabled && !duplicateError) {
      onUpload(selectedFile);
    }
  }, [selectedFile, uploading, disabled, duplicateError, onUpload]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (disabled || uploading) return;
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") {
        handleFileSelect(file);
      }
    },
    [disabled, uploading, handleFileSelect]
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleReset = useCallback(() => {
    setSelectedFile(null);
    setDuplicateError(null);
  }, []);

  return (
    <div className="space-y-3">
      {!selectedFile ? (
        <Card
          className="border-2 border-dashed border-muted-foreground/25 hover:border-primary/50 transition-colors cursor-pointer"
          onClick={() => {
            if (!disabled && !uploading) fileInputRef.current?.click();
          }}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          <CardContent className="flex flex-col items-center justify-center py-12">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleChange}
              disabled={disabled || uploading}
              className="hidden"
            />
            <Upload className="h-10 w-10 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              {disabled
                ? "Please wait — system is still initializing..."
                : "Drop a PDF here, or click to browse"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="flex items-center gap-3">
              <FileText className="h-8 w-8 text-primary shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                </p>
              </div>
            </div>
            {duplicateError && (
              <p className="text-sm text-destructive">{duplicateError}</p>
            )}
            <div className="flex gap-2">
              <Button
                onClick={triggerUpload}
                disabled={uploading || disabled || !!duplicateError}
                className="flex-1"
              >
                {uploading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-2" />
                    Upload
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setSelectedFile(null);
                  setDuplicateError(null);
                  fileInputRef.current?.click();
                }}
                disabled={uploading || disabled}
              >
                Change
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
