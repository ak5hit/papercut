import type { QueryResponse } from "@/lib/types";
import { SourceReferences } from "./source-references";
import { ExecutionTrace } from "./execution-trace";

interface AnswerDisplayProps {
  question: string;
  response: QueryResponse;
}

export function AnswerDisplay({ question, response }: AnswerDisplayProps) {
  return (
    <div className="space-y-4">
      <div className="bg-gray-50 border rounded-lg p-4">
        <p className="text-sm text-gray-500 mb-1">Question</p>
        <p className="font-medium text-gray-900">{question}</p>
      </div>

      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <h3 className="font-semibold text-gray-900 mb-2">Answer</h3>
        <div className="prose prose-sm max-w-none text-gray-800 whitespace-pre-wrap">
          {response.answer}
        </div>
      </div>

      {response.sources.length > 0 && (
        <SourceReferences sources={response.sources} />
      )}

      <ExecutionTrace trace={response.trace} />
    </div>
  );
}
