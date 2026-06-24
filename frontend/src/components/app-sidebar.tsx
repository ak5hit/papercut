"use client"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  FileText,
  Upload,
  Share2,
  Trash2,
  Loader2,
  CircleDot,
} from "lucide-react"
import type { Document } from "@/lib/types"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface AppSidebarProps {
  documents: Document[]
  loading: boolean
  isReady: boolean
  selectedDocId: string | null
  onSelectDoc: (id: string) => void
  onUploadClick: () => void
  onDelete: (id: string) => void
}

export function AppSidebar({
  documents,
  loading,
  isReady,
  selectedDocId,
  onSelectDoc,
  onUploadClick,
  onDelete,
}: AppSidebarProps) {
  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={onUploadClick}
          disabled={!isReady}
        >
          <Upload className="h-4 w-4" />
          Upload Document
        </Button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Documents ({documents.length})</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {loading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}
              {!loading && documents.length === 0 && (
                <p className="px-3 py-4 text-sm text-muted-foreground">
                  No documents uploaded yet.
                </p>
              )}
              {documents.map((doc) => (
                <SidebarMenuItem key={doc.id}>
                  <div
                    className={`group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer hover:bg-sidebar-accent ${
                      selectedDocId === doc.id ? "bg-sidebar-accent" : ""
                    }`}
                    onClick={() => onSelectDoc(doc.id)}
                  >
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-xs font-medium">
                        {doc.filename}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {doc.page_count} pages
                      </p>
                    </div>
                    <Badge
                      variant={
                        doc.embedding_status === "completed"
                          ? "default"
                          : doc.embedding_status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                      className="text-[9px] px-1 py-0 h-4"
                    >
                      {doc.embedding_status}
                    </Badge>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onSelectDoc(doc.id)
                            }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <Share2 className="h-3.5 w-3.5 text-muted-foreground hover:text-primary" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                          <p>View graph</p>
                        </TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onDelete(doc.id)
                            }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                          <p>Delete document</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t p-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {isReady ? (
            <>
              <CircleDot className="h-3 w-3 text-green-500" />
              <span>System ready</span>
            </>
          ) : (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Loading model...</span>
            </>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
