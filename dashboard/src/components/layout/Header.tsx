"use client";

import { useHealth } from "@/lib/api";
import { ProjectSwitcher } from "../ProjectSwitcher";
import { Activity, Server } from "lucide-react";
import { cn } from "@/lib/utils";

export function Header({
  selectedProjectId,
  onProjectChange
}: {
  selectedProjectId: string | null;
  onProjectChange: (id: string | null) => void;
}) {
  const { data: health } = useHealth();
  
  const isHealthy = health?.status === "ok";

  return (
    <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm sticky top-0 z-50">
      <div className="flex items-center gap-4 border-r border-gray-200 pr-4 mr-2">
        <div className="flex items-center gap-2">
          <div className="bg-blue-600 rounded p-1.5 shadow-sm">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <h1 className="font-bold text-gray-800 text-lg tracking-tight hidden sm:block">
            Agent Mind Bridge <span className="text-gray-400 font-normal">v4</span>
          </h1>
        </div>
      </div>
      
      <div className="flex-1 max-w-sm">
        <ProjectSwitcher selectedProjectId={selectedProjectId} onChange={onProjectChange} />
      </div>
      
      <div className="flex items-center gap-3 pl-4 border-l border-gray-200">
        <div className="flex items-center gap-2 px-2 py-1 bg-gray-50 border border-gray-200 rounded shadow-sm text-xs font-semibold text-gray-600 uppercase tracking-wider">
          <Server className="w-3.5 h-3.5" />
          API Status
          <div className={cn("w-2 h-2 rounded-full", isHealthy ? "bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]" : "bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]")} />
        </div>
      </div>
    </header>
  );
}
