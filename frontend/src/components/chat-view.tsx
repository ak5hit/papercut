"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { AnswerDisplay } from "./answer-display";
import { StreamingAnswer } from "./streaming-answer";
import type { ChatMessage } from "@/hooks/use-chat";

const SUGGESTED_QUESTIONS = [
  "What is the email address?",
  "Summarize the work experience",
  "Which companies did the candidate work at?",
  "List all people and the organizations they are connected to",
  "What is the relationship between Akshit Bansal and CRED?",
];

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (question: string) => void;
  onOpenGraph: (documentId: string) => void;
}

export function ChatView({ messages, loading, onSend, onOpenGraph }: ChatViewProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      const el = scrollRef.current;
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
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

  const handleSuggested = (q: string) => {
    setInput("");
    onSend(q);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)]">
      <ScrollArea ref={scrollRef} className="flex-1 pr-2">
        <div className="space-y-4 pb-4">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <h2 className="text-xl font-semibold mb-2">Ask anything about your documents</h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-md">
                Upload a document first, then ask questions about its content.
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSuggested(q)}
                    disabled={loading}
                    className="text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
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
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      <span className="text-sm text-muted-foreground">Thinking...</span>
                    </div>
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
                  <div className="max-w-[85%]">
                    <StreamingAnswer
                      content={msg.content}
                      sources={msg.response?.sources}
                      streaming={true}
                      onOpenGraph={onOpenGraph}
                    />
                  </div>
                ) : (
                  <div className="max-w-[85%]">
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
            className="shrink-0 self-end"
            size="icon"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
