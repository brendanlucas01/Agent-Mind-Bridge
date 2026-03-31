"use client";

import { useThreadEntries } from "@/lib/api";
import { X, MessageSquare, Star, Clock, User, Reply, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

export function ThreadDrawer({ 
  threadId, 
  onClose 
}: { 
  threadId: string | null; 
  onClose: () => void;
}) {
  const { data, error, isLoading } = useThreadEntries(threadId);

  if (!threadId) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className={cn(
          "fixed inset-0 bg-black/20 backdrop-blur-[2px] z-[100] transition-opacity duration-300",
          threadId ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div 
        className={cn(
          "fixed top-0 right-0 h-full w-[500px] bg-white shadow-2xl z-[101] flex flex-col transition-transform duration-300 ease-in-out border-l border-gray-200",
          threadId ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="p-4 bg-gray-50 border-b flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded text-blue-600">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-gray-800 line-clamp-1">{data?.thread?.title || "Loading thread..."}</h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs font-medium text-gray-500">{data?.thread?.project_name}</span>
                <span className="text-[10px] text-gray-400 font-bold">•</span>
                <span className={cn(
                  "text-[10px] uppercase font-bold tracking-wider",
                  data?.thread?.status === "resolved" ? "text-green-600" : "text-blue-600"
                )}>
                  {data?.thread?.status || "..."}
                </span>
              </div>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-gray-200 rounded-full transition-colors text-gray-500"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-neutral-50/50">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400 gap-2">
              <Clock className="w-8 h-8 animate-spin" />
              <span className="text-sm font-medium">Fetching discussion...</span>
            </div>
          ) : error ? (
            <div className="p-4 text-center text-red-500 bg-red-50 rounded border border-red-100">
              Failed to load entries
            </div>
          ) : (
            data?.entries.map((entry: any) => (
              <EntryCard key={entry.id} entry={entry} />
            ))
          )}
          
          {data?.entries?.length === 0 && (
            <div className="text-center py-12 text-gray-400 italic">No entries in this thread yet.</div>
          )}
        </div>
      </div>
    </>
  );
}

function EntryCard({ entry }: { entry: any }) {
  // Types: proposal=blue, feedback=amber, decision=green, note=grey
  const typeStyles = {
    proposal: "border-l-blue-500 bg-blue-50/30",
    feedback: "border-l-amber-500 bg-amber-50/30",
    decision: "border-l-green-500 bg-green-50/40",
    note: "border-l-gray-400 bg-gray-50/50",
  };

  const currentStyle = typeStyles[entry.type as keyof typeof typeStyles] || typeStyles.note;

  return (
    <div className={cn(
      "border border-gray-200 rounded-r-md px-4 py-3 shadow-sm border-l-4 transition-all relative",
      currentStyle,
      entry.pinned && "ring-1 ring-amber-400 bg-amber-50/20"
    )}>
      {entry.pinned && (
        <div className="absolute -top-2 -right-2 bg-amber-400 text-white rounded-full p-1 shadow-sm">
          <Star className="w-3 h-3 fill-white" />
        </div>
      )}
      
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {entry.agent_type === "human" ? (
            <User className="w-3.5 h-3.5 text-gray-400" />
          ) : (
            <CheckCircle className="w-3.5 h-3.5 text-blue-400" />
          )}
          <span className="font-bold text-sm text-gray-700">{entry.agent_name}</span>
          <span className="text-[10px] uppercase font-bold text-gray-400 bg-white px-1 border border-gray-100 rounded">
            {entry.type}
          </span>
        </div>
        <span className="text-[10px] text-gray-400 font-medium">
          {formatDistanceToNow(new Date(entry.created_at))} ago
        </span>
      </div>

      <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap font-sans">
        {entry.content}
      </div>
      
      {entry.reply_to && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-gray-500 bg-white/50 w-fit px-1.5 py-0.5 rounded border border-gray-100">
          <Reply className="w-3 h-3" />
          In reply to previous entry
        </div>
      )}
    </div>
  );
}
