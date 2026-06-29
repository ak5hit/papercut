"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, AlertCircle, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { AnswerDisplay } from "./answer-display";
import { StreamingAnswer } from "./streaming-answer";
import { QueryProgress } from "./query-progress";
import type { ChatMessage } from "@/hooks/use-chat";

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (question: string) => void;
  onOpenGraph: (documentId?: string) => void;
  onClear: () => void;
  hasDocuments: boolean;
}

export function ChatView({ messages, loading, onSend, onOpenGraph, onClear, hasDocuments }: ChatViewProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector<HTMLDivElement>(
        "[data-radix-scroll-area-viewport]"
      );
      if (viewport) {
        requestAnimationFrame(() => {
          viewport.scrollTop = viewport.scrollHeight;
        });
      }
    }
  }, [messages]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setInput("");
    onSend(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)]">
      {!isEmpty && (
        <div className="flex items-center justify-between mb-2 shrink-0">
          <h2 className="text-lg font-semibold">Chat</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              onClear();
              setInput("");
              inputRef.current?.focus();
            }}
            disabled={loading}
            className="gap-1.5 text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
            Clear chat
          </Button>
        </div>
      )}
      <ScrollArea ref={scrollRef} className="flex-1 pr-2">
        <div className="space-y-4 pb-4">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center py-20 text-center max-w-md mx-auto">
              {hasDocuments ? (
                <>
                  <h2 className="text-xl font-semibold mb-3">Ask anything about your documents</h2>
                  <p className="text-sm text-muted-foreground mb-2">
                    Click a document on the left to view its knowledge graph.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Or type a question below to start a conversation.
                  </p>
                </>
              ) : (
                <>
                  <h2 className="text-xl font-semibold mb-3">No documents yet</h2>
                  <p className="text-sm text-muted-foreground mb-2">
                    Upload a document to start exploring its knowledge graph.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Click the upload button in the sidebar to get started.
                  </p>
                </>
              )}
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "user" ? (
                  <div className="max-w-[80%] rounded-2xl px-4 py-2.5 bg-primary text-primary-foreground">
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                ) : msg.loading ? (
                  <Card className="max-w-[80%] p-4 bg-muted/30">
                    <QueryProgress progress={msg.progress} />
                  </Card>
                ) : msg.error ? (
                  <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-destructive/10 border border-destructive/30">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm text-destructive font-medium">Error</p>
                        <p className="text-xs text-destructive/80 mt-0.5">{msg.error}</p>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2 h-7 text-xs gap-1"
                          onClick={() => onSend(msg.content)}
                        >
                          <RefreshCw className="h-3 w-3" />
                          Retry
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : msg.streaming ? (
                  <div className="max-w-[85%] animate-in fade-in duration-500">
                    <StreamingAnswer
                      content={msg.content}
                      sources={msg.response?.sources}
                      streaming={true}
                      onOpenGraph={onOpenGraph}
                    />
                  </div>
                ) : (
                  <div className="max-w-[85%] animate-in fade-in duration-500">
                    <AnswerDisplay response={msg.response!} onOpenGraph={onOpenGraph} />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      <div className="sticky bottom-0 bg-background pt-3 border-t mt-auto">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            disabled={loading}
            className="min-h-[52px] max-h-32 resize-none"
          />
          <Button
            type="submit"
            disabled={loading || !input.trim()}
            className="shrink-0 h-[52px] w-[52px] self-end"
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
