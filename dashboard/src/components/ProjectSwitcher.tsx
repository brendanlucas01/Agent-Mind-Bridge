"use client";

import { useProjects } from "@/lib/api";
import { FolderGit2, Check, ChevronDown } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

export function ProjectSwitcher({
  selectedProjectId,
  onChange
}: {
  selectedProjectId: string | null;
  onChange: (id: string | null) => void;
}) {
  const { data: projects, error } = useProjects();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Set first project as default if none selected
  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProjectId) {
      onChange(projects[0].id);
    }
  }, [projects, selectedProjectId, onChange]);

  if (error) return <div className="text-red-500 text-sm">Error loading projects</div>;
  if (!projects) return <div className="text-gray-400 text-sm">Loading projects...</div>;

  const currentProject = projects.find((p: any) => p.id === selectedProjectId);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border border-gray-300 rounded shadow-sm hover:bg-gray-100 transition-colors"
      >
        <FolderGit2 className="w-4 h-4 text-blue-600" />
        <span className="font-medium text-sm text-gray-800">
          {currentProject ? currentProject.name : "Select Project"}
        </span>
        <ChevronDown className="w-4 h-4 text-gray-500 ml-2" />
      </button>

      {isOpen && (
        <div className="absolute top-10 left-0 w-64 bg-white border border-gray-200 rounded shadow-lg z-50 overflow-hidden">
          <div className="bg-gray-100 px-3 py-2 border-b border-gray-200">
            <h4 className="text-xs font-semibold text-gray-500 uppercase">Your Projects</h4>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {projects.map((p: any) => (
              <button
                key={p.id}
                onClick={() => {
                  onChange(p.id);
                  setIsOpen(false);
                }}
                className={cn(
                  "w-full text-left px-4 py-2 hover:bg-blue-50 transition-colors flex items-center justify-between group",
                  selectedProjectId === p.id ? "bg-blue-50" : ""
                )}
              >
                <div>
                  <div className="font-medium text-sm text-gray-800 group-hover:text-blue-700">{p.name}</div>
                  <div className="text-xs text-gray-500 flex gap-2 mt-0.5">
                    <span>{p.thread_count} threads</span>
                    <span>•</span>
                    <span>{p.agent_count} agents</span>
                  </div>
                </div>
                {selectedProjectId === p.id && <Check className="w-4 h-4 text-blue-600" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
