"use client";

import { useHandoffs } from "@/lib/api";
import { Coffee, ArrowRight, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export function HandoffPanel({ projectId }: { projectId: string | null }) {
  const { data: handoffs, error, isLoading } = useHandoffs(projectId);

  if (!projectId) return null;
  if (isLoading) return <div className="p-4 text-gray-400">Loading handoffs...</div>;
  if (error) return <div className="p-4 text-red-500">Error loading handoffs</div>;

  const handoff = handoffs?.[0];

  return (
    <div className="bg-white border rounded shadow-sm flex flex-col h-full max-h-[300px]">
      <div className="bg-gray-100 border-b px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Coffee className="w-4 h-4 text-orange-600" />
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Latest Handoff</h3>
        </div>
        {handoff && (
          <span className={cn(
            "text-[10px] uppercase font-bold px-2 py-0.5 rounded",
            handoff.acknowledged_by ? "bg-green-100 text-green-700" : "bg-orange-100 text-orange-700 animate-pulse"
          )}>
            {handoff.acknowledged_by ? "Acknowledged" : "Pending"}
          </span>
        )}
      </div>

      <div className="p-3 overflow-y-auto flex-1 text-sm bg-gray-50/50">
        {!handoff ? (
          <div className="text-gray-500 text-center py-4 italic">No recent handoffs</div>
        ) : (
          <div className="space-y-4">
            <div className="flex justify-between items-start border-b pb-2">
              <div>
                <span className="font-semibold text-gray-800">{handoff.from_agent_name}</span>
                <span className="text-gray-500 text-xs ml-2">{handoff.created_at_human}</span>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <h4 className="text-xs font-bold uppercase text-gray-500 mb-1">Summary</h4>
                <p className="text-gray-700">{handoff.summary}</p>
              </div>

              {handoff.in_progress && (
                <div>
                  <h4 className="text-xs font-bold uppercase text-gray-500 mb-1 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3" /> In Progress
                  </h4>
                  <p className="text-gray-700 whitespace-pre-wrap">{handoff.in_progress}</p>
                </div>
              )}

              {handoff.blockers && (
                <div className="bg-red-50 p-2 rounded border border-red-100">
                  <h4 className="text-xs font-bold uppercase text-red-600 mb-1 flex items-center gap-1">
                    <XCircle className="w-3 h-3" /> Blockers
                  </h4>
                  <p className="text-red-700 whitespace-pre-wrap">{handoff.blockers}</p>
                </div>
              )}

              {handoff.next_steps && (
                <div>
                  <h4 className="text-xs font-bold uppercase text-gray-500 mb-1">Suggested Next Steps</h4>
                  <p className="text-gray-700 whitespace-pre-wrap">{handoff.next_steps}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
