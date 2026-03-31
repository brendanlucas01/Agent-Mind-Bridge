"use client";

import { useSkills } from "@/lib/api";
import { BookOpen, Tag } from "lucide-react";

export function SkillsPanel({ projectId }: { projectId: string | null }) {
  const { data: skills, error, isLoading } = useSkills(projectId);

  if (!projectId) return null;
  if (isLoading) return <div className="p-4 text-gray-400">Loading skills...</div>;
  if (error) return <div className="p-4 text-red-500">Error loading skills</div>;

  return (
    <div className="bg-white border rounded shadow-sm flex flex-col h-full max-h-[300px]">
      <div className="bg-gray-100 border-b px-3 py-2 flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-purple-600" />
        <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Global Skills</h3>
        <span className="bg-white px-1.5 py-0.5 rounded text-[10px] font-bold text-gray-500 shadow-sm border border-gray-200 ml-auto">
          {skills?.length || 0}
        </span>
      </div>

      <div className="p-0 overflow-y-auto flex-1 bg-gray-50/30">
        {!skills || skills.length === 0 ? (
          <div className="text-gray-500 text-center py-6 italic text-sm">No global skills found</div>
        ) : (
          <div className="divide-y divide-gray-100 border-b border-gray-100">
            {skills.map((skill: any) => (
              <div key={skill.id} className="p-3 hover:bg-white transition-colors">
                <div className="flex items-start justify-between mb-1">
                  <span className="font-semibold text-gray-800 text-sm truncate pr-2">{skill.name}</span>
                  <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200 shadow-sm uppercase font-bold tracking-wider shrink-0 mt-0.5">
                    v{skill.version}
                  </span>
                </div>
                {skill.description && (
                  <p className="text-[11px] text-gray-600 line-clamp-2 leading-snug">{skill.description}</p>
                )}
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex items-center gap-1 text-[10px] uppercase font-bold text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded border border-gray-200 shadow-sm">
                    <Tag className="w-3 h-3 text-gray-400" />
                    {skill.skill_type}
                  </div>
                  {skill.scope && (
                    <div className="text-[10px] text-gray-400 font-medium ml-auto">
                      Scope: {skill.scope}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
