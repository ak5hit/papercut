"use client"

import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { ThemeToggle } from "@/components/theme-toggle"
import { Network } from "lucide-react"

export function SiteHeader() {
  return (
    <header className="flex h-14 items-center gap-2 border-b px-4 sticky top-0 z-50 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <Network className="h-5 w-5 text-primary" />
      <span className="font-semibold text-sm">Graph Intelligence</span>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
      </div>
    </header>
  )
}
