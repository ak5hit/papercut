"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useGraph } from "@/hooks/use-graph";

const NODE_COLORS: Record<string, string> = {
  Person: "#3b82f6",
  Company: "#22c55e",
  Organization: "#22c55e",
  Email: "#f97316",
  Phone: "#a855f7",
  URL: "#a855f7",
  Skill: "#14b8a6",
  Location: "#ef4444",
  Document: "#6366f1",
  Chunk: "#9ca3af",
};

const DEFAULT_COLOR = "#6366f1";

interface GraphViewProps {
  documentId: string | null;
  documentName?: string;
  containerClassName?: string;
}

export function GraphView({ documentId, documentName, containerClassName = "h-[500px]" }: GraphViewProps) {
  const isFillHeight = containerClassName.includes("h-full");
  const { graphData, loading, error } = useGraph(documentId);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<any>(null);
  const [cytoscapeLoaded, setCytoscapeLoaded] = useState(false);

  useEffect(() => {
    import("cytoscape").then(() => setCytoscapeLoaded(true));
  }, []);

  const elements = useMemo(() => {
    if (!graphData) return { nodes: [] as any[], edges: [] as any[] };

    const nodes = graphData.nodes.map((n) => ({
      data: {
        id: n.entity_id,
        label: n.label,
        name: n.entity_id,
        color: NODE_COLORS[n.label] || DEFAULT_COLOR,
      },
    }));

    const edges = graphData.edges.map((e, i) => ({
      data: {
        id: `edge-${i}`,
        source: e.source,
        target: e.target,
        label: e.type,
      },
    }));

    return { nodes, edges };
  }, [graphData]);

  useEffect(() => {
    if (!containerRef.current || !cytoscapeLoaded || !elements.nodes.length) return;
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    import("cytoscape").then((cytoscape) => {
      const cy = (cytoscape as any).default || cytoscape;
      const instance = cy({
        container: containerRef.current,
        elements: [
          ...elements.nodes.map((n) => ({ data: n.data })),
          ...elements.edges.map((e) => ({ data: e.data })),
        ],
        style: [
          {
            selector: "node",
            style: {
              "background-color": "data(color)",
              label: "data(name)",
              "text-valign": "center",
              "text-halign": "center",
              "font-size": "10px",
              color: "#fff",
              "text-wrap": "wrap",
              "text-max-width": "80px",
              width: "label",
              height: "label",
              padding: "12px",
              shape: "round-rectangle",
              "border-width": 2,
              "border-color": "#ffffff33",
            },
          },
          {
            selector: "edge",
            style: {
              width: 2,
              "line-color": "#94a3b8",
              "target-arrow-color": "#94a3b8",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": "8px",
              "text-rotation": "autorotate",
              color: "#94a3b8",
              "text-background-color": "#ffffff",
              "text-background-padding": "2px",
              "text-background-shape": "round-rectangle",
            },
          },
          {
            selector: ":selected",
            style: {
              "border-width": 4,
              "border-color": "#3b82f6",
            },
          },
        ],
        layout: { name: "cose", animate: true, padding: 30 },
        minZoom: 0.1,
        maxZoom: 5,
        wheelSensitivity: 0.5,
      });

      cyRef.current = instance;
    });

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [elements, cytoscapeLoaded]);

  if (!documentId) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-20">
          <p className="text-muted-foreground text-sm">
            Select a document from the sidebar to view its knowledge graph.
          </p>
        </CardContent>
      </Card>
    );
  }

  const cardClass = isFillHeight ? "h-full flex flex-col overflow-hidden" : "overflow-hidden";

  if (loading) {
    return (
      <Card className={cardClass}>
        <CardHeader>
          <CardTitle className="text-sm">Loading graph...</CardTitle>
        </CardHeader>
        <CardContent className={isFillHeight ? "flex-1 min-h-0" : ""}>
          <Skeleton className={`${containerClassName} w-full`} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cardClass}>
        <CardContent className={`flex flex-col items-center justify-center py-20 ${isFillHeight ? "flex-1 min-h-0" : ""}`}>
          <p className="text-destructive text-sm">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <Card className={cardClass}>
        <CardContent className={`flex flex-col items-center justify-center py-20 ${isFillHeight ? "flex-1 min-h-0" : ""}`}>
          <p className="text-muted-foreground text-sm">
            No graph data found for this document.
          </p>
          <a
            href={`/api/graph/documents/${documentId}/stats`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline mt-2"
          >
            view graph stats
          </a>
        </CardContent>
      </Card>
    );
  }

  const uniqueLabels = [...new Set(graphData.nodes.map((n) => n.label))];

  return (
    <Card className={cardClass}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">
            {documentName || "Knowledge Graph"}
          </CardTitle>
          <div className="flex gap-2 items-center">
            <Badge variant="secondary" className="text-xs">
              {graphData.nodes.length} nodes
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {graphData.edges.length} edges
            </Badge>
            <a
              href={`/api/graph/documents/${documentId}/stats`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
            >
              stats
            </a>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          {uniqueLabels.map((label) => (
            <div key={label} className="flex items-center gap-1.5">
              <div
                className="h-3 w-3 rounded-full"
                style={{
                  backgroundColor: NODE_COLORS[label] || DEFAULT_COLOR,
                }}
              />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      </CardHeader>
      <CardContent className={isFillHeight ? "flex-1 min-h-0" : ""}>
        <div
          ref={containerRef}
          className={`border rounded-lg overflow-hidden bg-muted/20 ${containerClassName}`}
        />
      </CardContent>
    </Card>
  );
}
