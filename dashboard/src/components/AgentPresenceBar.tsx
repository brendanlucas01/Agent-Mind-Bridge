"use client";

import { useAgents } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Bot, User, CheckCircle2, Clock, AlertCircle, Eye } from "lucide-react";

export function AgentPresenceBar() {
  const { data: agents, error } = useAgents();

  if (error) return <div className="p-4 text-red-500">Failed to load agents</div>;
  if (!agents) return <div className="p-4 text-gray-400">Loading presence...</div>;

  return (
    <div className="bg-white border-b border-gray-200 p-2 overflow-x-auto flex gap-4 shadow-sm relative z-10">
      <div className="flex items-center gap-2 pl-2">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Agents</h3>
      </div>
      <div className="flex gap-3">
        {agents.map((agent: any) => (
          <AgentBadge key={agent.id} agent={agent} />
        ))}
      </div>
    </div>
  );
}

function AgentBadge({ agent }: { agent: any }) {
  const isHuman = agent.type === "human";
  
  // Status colors: working=green, idle=grey, blocked=red, reviewing=amber
  let statusColor = "bg-gray-100 border-gray-300 text-gray-600";
  let statusDot = "bg-gray-400";
  let Icon = isHuman ? User : Bot;

  if (agent.status === "working") {
    statusColor = "bg-[#f0f9ff] border-[#bae6fd] text-[#0369a1]";
    statusDot = "bg-emerald-500";
  } else if (agent.status === "blocked") {
    statusColor = "bg-red-50 border-red-200 text-red-700";
    statusDot = "bg-red-500";
  } else if (agent.status === "reviewing") {
    statusColor = "bg-amber-50 border-amber-200 text-amber-700";
    statusDot = "bg-amber-500";
  }

  return (
    <div className={cn("flex flex-col border rounded-md px-3 py-1.5 min-w-[160px] shadow-sm transition-all hover:shadow-md", statusColor)}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-1.5 font-medium text-sm">
          <Icon className="w-4 h-4 opacity-70" />
          <span>{agent.name}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] uppercase font-bold tracking-wider opacity-70">{agent.status}</span>
          <div className={cn("w-2 h-2 rounded-full shadow-inner ring-1 ring-black/10", statusDot)} />
        </div>
      </div>
      
      {agent.current_task ? (
        <div className="text-xs opacity-80 truncate" title={agent.current_task}>
          {agent.current_task}
        </div>
      ) : (
        <div className="text-xs opacity-50 italic">No active task</div>
      )}
      
      {agent.project_name && (
        <div className="text-[10px] mt-1 opacity-60 font-medium">
          @ {agent.project_name}
        </div>
      )}
    </div>
  );
}
