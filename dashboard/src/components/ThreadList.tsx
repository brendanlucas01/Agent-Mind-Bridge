"use client";

import { useThreads } from "@/lib/api";
import { MessageCircle, CheckCircle } from "lucide-react";

export function ThreadList({ 
  projectId,
  onThreadClick
}: { 
  projectId: string | null;
  onThreadClick: (threadId: string) => void;
}) {
  const { data: threads, error, isLoading } = useThreads(projectId);

  if (!projectId) return null;
  if (isLoading) return <div className="p-4 text-gray-400">Loading threads...</div>;
  if (error) return <div className="p-4 text-red-500">Error loading threads</div>;

  return (
    <div className="bg-white border rounded shadow-sm flex flex-col h-full max-h-[300px]">
      <div className="bg-gray-100 border-b px-3 py-2 flex items-center gap-2">
        <MessageCircle className="w-4 h-4 text-indigo-600" />
        <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Active Threads</h3>
      </div>

      <div className="p-0 overflow-y-auto flex-1 bg-gray-50/30">
        {!threads || threads.length === 0 ? (
          <div className="text-gray-500 text-center py-6 italic text-sm">No threads found</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {threads.map((thread: any) => (
              <button 
                key={thread.id} 
                onClick={() => onThreadClick(thread.id)}
                className="w-full text-left p-3 hover:bg-white transition-colors group"
              >
                <div className="flex items-start justify-between mb-1 gap-2">
                  <span className="font-semibold text-gray-800 text-sm line-clamp-1 group-hover:text-blue-600 transition-colors uppercase tracking-tight">{thread.title}</span>
                  {thread.status === "resolved" ? (
                      <CheckCircle className="w-3.5 h-3.5 text-green-500 shrink-0" />
                  ) : (
                      <div className="w-2 h-2 rounded-full bg-blue-500 mt-1 shrink-0" />
                  )}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <div className="text-[10px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded font-bold uppercase">
                    {thread.entry_count} entries
                  </div>
                  {thread.last_entry_agent && (
                    <div className="text-[10px] text-gray-400 font-medium italic">
                      {thread.last_entry_agent}
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
