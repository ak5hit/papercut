"use client";

// Chat history is session-only. Refreshing the page resets the conversation.
// Persisting sessions across refreshes (localStorage / backend sessions table)
// is a deliberate non-goal for this phase.

import { useState, useCallback, useRef } from "react";
import { streamChatMessage } from "@/lib/api-client";
import type { ChatRequestMessage, ExecutionTrace, QueryResponse, SourceReference } from "@/lib/types";

const EMPTY_TRACE = { strategy: "", steps: [], structured_results_count: 0, semantic_results_count: 0, graph_results_count: 0 };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: QueryResponse;
  loading?: boolean;
  streaming?: boolean;
  error?: string;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || loading) return;

      setLoading(true);
      setError(null);

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };

      const placeholderId = crypto.randomUUID();
      const placeholder: ChatMessage = {
        id: placeholderId,
        role: "assistant",
        content: "",
        loading: true,
      };

      setMessages((prev) => [...prev, userMessage, placeholder]);

      const apiMessages: ChatRequestMessage[] = [
        ...messagesRef.current.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content || "",
        })),
        { role: "user" as const, content: trimmed },
      ];

      try {
        let currentTrace: ExecutionTrace | null = null;
        let currentSources: SourceReference[] = [];
        let accumulatedContent = "";
        let finalSessionId = sessionIdRef.current;

        for await (const event of streamChatMessage(finalSessionId, apiMessages)) {
          switch (event.type) {
            case "meta": {
              finalSessionId = event.session_id as string;
              setSessionId(finalSessionId);
              break;
            }
            case "trace": {
              currentTrace = event as unknown as ExecutionTrace;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === placeholderId
                    ? {
                        ...m,
                        response: {
                          answer: accumulatedContent,
                          sources: currentSources,
                          trace: currentTrace || EMPTY_TRACE,
                        },
                      }
                    : m,
                ),
              );
              break;
            }
            case "sources": {
              currentSources = (event.sources as SourceReference[]) || [];
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === placeholderId
                    ? {
                        ...m,
                        streaming: true,
                        response: {
                          answer: accumulatedContent,
                          sources: currentSources,
                          trace: currentTrace || EMPTY_TRACE,
                        },
                      }
                    : m,
                ),
              );
              break;
            }
            case "token": {
              accumulatedContent += (event.text as string) || "";
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === placeholderId
                    ? {
                        ...m,
                        content: accumulatedContent,
                        streaming: true,
                        loading: false,
                        response: {
                          answer: accumulatedContent,
                          sources: currentSources,
                          trace: currentTrace || EMPTY_TRACE,
                        },
                      }
                    : m,
                ),
              );
              break;
            }
            case "done": {
              const serverMessages = event.messages as ChatRequestMessage[] | undefined;
              const serverAnswer = serverMessages
                ? serverMessages.filter((m) => m.role === "assistant").pop()?.content || accumulatedContent
                : accumulatedContent;
              setSessionId(event.session_id as string);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === placeholderId
                    ? {
                        id: m.id,
                        role: "assistant",
                        content: serverAnswer,
                        streaming: false,
                        loading: false,
                        response: {
                          answer: serverAnswer,
                          sources: currentSources,
                          trace: currentTrace || EMPTY_TRACE,
                        },
                      }
                    : m,
                ),
              );
              break;
            }
            case "error": {
              const errMsg = (event.message as string) || "Chat request failed";
              setError(errMsg);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === placeholderId
                    ? {
                        id: m.id,
                        role: "assistant" as const,
                        content: "",
                        error: errMsg,
                        loading: false,
                      }
                    : m,
                ),
              );
              break;
            }
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Chat request failed";
        setError(msg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === placeholderId
              ? {
                  id: m.id,
                  role: "assistant" as const,
                  content: "",
                  error: msg,
                  loading: false,
                }
              : m,
          ),
        );
      } finally {
        setLoading(false);
      }
    },
    [loading],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setLoading(false);
    setError(null);
  }, []);

  return { messages, sessionId, loading, error, send, clear };
}
