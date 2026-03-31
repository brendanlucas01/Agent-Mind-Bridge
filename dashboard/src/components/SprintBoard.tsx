"use client";

import { useSprint } from "@/lib/api";
import { LayoutList, CheckCircle2, Clock, PlayCircle, StopCircle, Lock, PauseCircle, ChevronRight, User } from "lucide-react";
import { cn } from "@/lib/utils";

const columns = [
  { id: "backlog", title: "Backlog", icon: LayoutList, color: "text-gray-500", bg: "bg-gray-50", border: "border-gray-200" },
  { id: "todo", title: "To Do", icon: StopCircle, color: "text-blue-500", bg: "bg-blue-50/30", border: "border-blue-200" },
  { id: "in_progress", title: "In Progress", icon: PlayCircle, color: "text-emerald-500", bg: "bg-emerald-50/30", border: "border-emerald-200" },
  { id: "review", title: "Review", icon: PauseCircle, color: "text-amber-500", bg: "bg-amber-50/30", border: "border-amber-200" },
  { id: "blocked", title: "Blocked", icon: Lock, color: "text-red-500", bg: "bg-red-50/30", border: "border-red-200" },
  { id: "done", title: "Done", icon: CheckCircle2, color: "text-indigo-500", bg: "bg-indigo-50/30", border: "border-indigo-200" },
];

export function SprintBoard({ projectId }: { projectId: string | null }) {
  const { data, error, isLoading } = useSprint(projectId);

  if (!projectId) return null;
  if (isLoading) return <div className="p-8 text-center text-gray-400 font-medium">Loading Sprint Board...</div>;
  if (error) return <div className="p-8 text-center text-red-500 font-medium">Failed to load Sprint Board</div>;

  if (!data?.sprint) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-white rounded border border-gray-200 shadow-sm h-full">
        <LayoutList className="w-12 h-12 text-gray-300 mb-4" />
        <h3 className="text-lg font-semibold text-gray-700">No Active Sprint</h3>
        <p className="text-gray-500 text-sm mt-1">Start a sprint in your CLI session to see the kanban board.</p>
      </div>
    );
  }

  const { sprint, board, summary } = data;

  return (
    <div className="flex flex-col h-full rounded border border-gray-200 bg-gray-50 shadow-sm overflow-hidden relative">
      <div className="bg-white border-b px-4 py-3 flex justify-between items-center shadow-sm z-10 shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-gray-800">{sprint.name}</h2>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-700 border border-emerald-200 shadow-sm">
              Active
            </span>
          </div>
          {sprint.goal && <p className="text-sm text-gray-500 mt-1 flex items-center gap-1"><ChevronRight className="w-3 h-3"/> {sprint.goal}</p>}
        </div>
        <div className="flex items-center gap-6 text-sm">
          <div className="text-right">
            <div className="text-xs text-gray-500 font-medium uppercase tracking-wider">Progress</div>
            <div className="font-semibold text-gray-800">
              {summary.done} / {summary.total} Tasks
            </div>
          </div>
          <div className="w-32 h-2 rounded-full border border-gray-200 overflow-hidden bg-gray-100 shadow-inner">
            <div 
              className="h-full bg-blue-500 transition-all duration-500" 
              style={{ width: `${summary.total > 0 ? (summary.done / summary.total) * 100 : 0}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-x-auto p-4 gap-4 items-start min-h-0">
        {columns.map(col => {
          const tasks = board[col.id] || [];
          return (
            <div key={col.id} className={cn("min-w-[280px] w-[280px] max-w-[280px] rounded-md border flex flex-col shadow-sm max-h-full h-[calc(100vh-14rem)]", col.bg, col.border)}>
              <div className="px-3 py-2 border-b bg-white/50 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-1.5 font-semibold text-sm">
                  <col.icon className={cn("w-4 h-4", col.color)} />
                  <span className="text-gray-700">{col.title}</span>
                </div>
                <span className="bg-white px-2 py-0.5 rounded text-xs font-bold text-gray-500 shadow-sm border border-gray-200">{tasks.length}</span>
              </div>
              <div className="p-2 overflow-y-auto space-y-2 flex-1 scrollbar-thin scrollbar-thumb-gray-200 hover:scrollbar-thumb-gray-300">
                {tasks.map((task: any) => (
                  <TaskCard key={task.id} task={task} />
                ))}
                {tasks.length === 0 && (
                  <div className="p-4 text-center text-xs text-gray-400 font-medium italic border-2 border-dashed border-gray-200 rounded">
                    Empty
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: any }) {
  const priorityColors = {
    critical: "bg-red-500 text-white border-red-600 shadow-red-200",
    high: "bg-orange-100 text-orange-700 border-orange-200 shadow-sm",
    medium: "bg-blue-50 text-blue-700 border-blue-200 shadow-sm",
    low: "bg-gray-100 text-gray-600 border-gray-200 shadow-sm",
  };

  const pColor = priorityColors[task.priority as keyof typeof priorityColors] || priorityColors.medium;

  return (
    <div className="bg-white border-x border-b border-t-2 border-t-gray-300 rounded p-2.5 shadow hover:shadow-md transition-shadow cursor-default relative overflow-hidden">
      <div className="flex flex-col gap-1.5">
        <span className="font-semibold text-[13px] text-gray-800 leading-snug break-words">
          {task.title}
        </span>
      </div>
      
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-100/80">
        <span className={cn("text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border leading-none tracking-wide", pColor)}>
          {task.priority || 'medium'}
        </span>
        
        {task.assigned_to_name && (
          <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-50/80 px-1.5 py-0.5 rounded border border-gray-200" title={`Assigned to ${task.assigned_to_name}`}>
            <User className="w-3 h-3 opacity-70" />
            <span className="font-medium truncate max-w-[80px]">{task.assigned_to_name}</span>
          </div>
        )}
      </div>
      
      {task.blocked_reason && (
        <div className="mt-2 text-[11px] text-red-700 bg-red-50/50 border border-red-100 rounded p-1.5 flex gap-1.5 items-start">
          <Lock className="w-3 h-3 mt-0.5 flex-shrink-0 text-red-500" />
          <span className="line-clamp-2 leading-tight">{task.blocked_reason}</span>
        </div>
      )}
      
      {task.depends_on && task.depends_on.length > 0 && (
        <div className="mt-1 text-[10px] text-blue-600 font-medium tracking-wide">
           Wait: {task.depends_on.length} upstream
        </div>
      )}
    </div>
  );
}
