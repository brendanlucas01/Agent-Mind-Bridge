"use client";

import { useState } from "react";
import { Header } from "@/components/layout/Header";
import { AgentPresenceBar } from "@/components/AgentPresenceBar";
import { SprintBoard } from "@/components/SprintBoard";
import { HandoffPanel } from "@/components/HandoffPanel";
import { ActivityStream } from "@/components/ActivityStream";
import { ThreadList } from "@/components/ThreadList";
import { SkillsPanel } from "@/components/SkillsPanel";
import { ThreadDrawer } from "@/components/ThreadDrawer";

export default function Dashboard() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-neutral-100 flex flex-col font-sans text-slate-800 selection:bg-blue-200">
      <Header selectedProjectId={selectedProjectId} onProjectChange={setSelectedProjectId} />
      <AgentPresenceBar />
      
      <main className="flex-1 p-4 flex gap-4 overflow-hidden h-[calc(100vh-8rem)]">
        {selectedProjectId ? (
          <>
            <div className="flex-1 w-full min-w-0">
              <SprintBoard projectId={selectedProjectId} />
            </div>
            
            <div className="w-[340px] shrink-0 flex flex-col gap-4 overflow-y-auto pr-1 pb-4 scrollbar-thin scrollbar-thumb-gray-300">
              <HandoffPanel projectId={selectedProjectId} />
              <ActivityStream projectId={selectedProjectId} onThreadClick={setActiveThreadId} />
              <ThreadList projectId={selectedProjectId} onThreadClick={setActiveThreadId} />
              <SkillsPanel projectId={selectedProjectId} />
            </div>

            <ThreadDrawer 
              threadId={activeThreadId} 
              onClose={() => setActiveThreadId(null)} 
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-gray-500 bg-white/50 rounded border border-gray-200 border-dashed m-4 shadow-sm">
            <div className="bg-gray-100 p-4 rounded-full mb-4">
              <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">No Project Selected</h2>
            <p className="max-w-md mx-auto text-gray-500">Pick a project from the top navigation to view its sprint board, activity stream, and active threads.</p>
          </div>
        )}
      </main>
    </div>
  );
}
