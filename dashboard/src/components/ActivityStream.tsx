"use client";

import { useActivity } from "@/lib/api";
import { MessageSquare, Mail, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export function ActivityStream({ 
  projectId,
  onThreadClick
}: { 
  projectId: string | null;
  onThreadClick: (threadId: string) => void;
}) {
  const { data: activity, error, isLoading } = useActivity(projectId);

  if (!projectId) return null;
  if (isLoading) return <div className="p-4 text-gray-400">Loading activity...</div>;
  if (error) return <div className="p-4 text-red-500">Error loading activity</div>;

  return (
    <div className="bg-white border rounded shadow-sm flex flex-col h-full max-h-[400px]">
      <div className="bg-gray-100 border-b px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-blue-600" />
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Live Activity Stream</h3>
        </div>
        <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-700">
          Last 30 Events
        </span>
      </div>

      <div className="p-0 overflow-y-auto flex-1 bg-gray-50/30">
        {!activity || activity.length === 0 ? (
          <div className="text-gray-500 text-center py-8 italic text-sm">No recent activity found.</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {activity.map((item: any, idx: number) => {
              if (item.type === "entry") {
                return (
                  <button 
                    key={`${item.entry_id}-${idx}`} 
                    onClick={() => onThreadClick(item.thread_id)}
                    className="w-full text-left"
                  >
                    <EntryItem item={item} />
                  </button>
                );
              } else {
                return <MessageItem key={`${item.timestamp}-${idx}`} item={item} />;
              }
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function EntryItem({ item }: { item: any }) {
  return (
    <div className="p-3 hover:bg-white transition-colors">
      <div className="flex justify-between items-start mb-1 gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-semibold text-gray-800 text-sm whitespace-nowrap">{item.agent_name}</span>
          <span className="text-gray-500 text-xs">{item.action}</span>
          <span className="text-xs font-medium text-blue-600 truncate max-w-[200px]">"{item.thread_title}"</span>
        </div>
        <span className="text-[10px] text-gray-400 whitespace-nowrap">{item.timestamp_human}</span>
      </div>
      <div className="text-sm text-gray-600 line-clamp-2 mt-1 leading-snug border-l-2 border-gray-200 pl-2">
        {item.content_preview}
      </div>
    </div>
  );
}

function MessageItem({ item }: { item: any }) {
  const isHighPriority = item.priority_flag;
  
  return (
    <div className={cn("p-3 transition-colors", isHighPriority ? "bg-red-50/50 hover:bg-red-50" : "hover:bg-white")}>
      <div className="flex justify-between items-start mb-1 gap-2">
        <div className="flex items-center gap-1.5">
          {isHighPriority ? <AlertTriangle className="w-3.5 h-3.5 text-red-500" /> : <Mail className="w-3.5 h-3.5 text-amber-500" />}
          <span className="font-semibold text-gray-800 text-sm">{item.from_agent}</span>
          <span className="text-gray-500 text-xs">messaged</span>
          <span className="font-semibold text-gray-700 text-sm">{item.to_agent}</span>
        </div>
        <span className="text-[10px] text-gray-400">{item.timestamp_human}</span>
      </div>
      
      <div className="flex items-center gap-2 mt-1 border-l-2 border-amber-200 pl-2">
        {!item.is_read && (
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 flex-shrink-0" />
        )}
        <span className={cn("text-sm line-clamp-1", isHighPriority ? "text-red-700 font-medium" : "text-gray-700 font-medium")}>
          {item.subject}
        </span>
      </div>
    </div>
  );
}
