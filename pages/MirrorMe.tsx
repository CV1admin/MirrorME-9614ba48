import React, { useState } from 'react';
import ChatInterface from '../components/ChatInterface';
import AraChatPanel from '../components/AraChatPanel';
import { SimulationState } from '../types';

interface MirrorMeProps {
  simState: SimulationState;
}

const MirrorMe: React.FC<MirrorMeProps> = ({ simState }) => {
  const [chatMode, setChatMode] = useState<'local' | 'ara'>('local');

  return (
    <div className="h-full grid grid-cols-1 xl:grid-cols-3 gap-0">
      <div className="xl:col-span-2 p-8 overflow-y-auto border-r border-slate-800 bg-slate-950/30">
        <h2 className="text-3xl font-bold text-slate-100 mb-2">MirrorMe</h2>
        <p className="text-slate-400 mb-8">Personal intelligence layer for reflection, planning, and local AI support.</p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-cyan-400 font-bold mb-3">User Profile</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Identity</span><span className="text-slate-200">Primary Researcher</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Focus Domain</span><span className="text-slate-200">Civilisation Engineering</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Current Mode</span><span className="text-emerald-400">Exploration</span></div>
            </div>
          </section>

          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-cyan-400 font-bold mb-3">Memory</h3>
            <ul className="space-y-2 text-sm text-slate-300">
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Local long-term notes and insight logs</li>
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Session summaries and decision trace</li>
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Skill map and pattern library</li>
            </ul>
          </section>

          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-cyan-400 font-bold mb-3">Goals</h3>
            <ul className="space-y-2 text-sm text-slate-300">
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Build robust local-first AI workflow</li>
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Validate Thin Line Theory claims</li>
              <li className="p-2 rounded bg-slate-950 border border-slate-800">Increase civilisation score over time</li>
            </ul>
          </section>

          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 className="text-xs uppercase tracking-widest text-cyan-400 font-bold mb-3">Personal Development Plan</h3>
            <ol className="space-y-2 text-sm text-slate-300 list-decimal list-inside">
              <li>Weekly learning sprint with measurable outcomes</li>
              <li>Daily reflective prompts from local AI assistant</li>
              <li>Monthly review with evidence-backed adjustments</li>
            </ol>
          </section>
        </div>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
          <h3 className="text-xs uppercase tracking-widest text-cyan-400 font-bold mb-2">Local AI Assistant</h3>
          <p className="text-sm text-slate-400">Use the assistant in local mode from Settings to keep cognition data on-device.</p>
          <div className="mt-4 text-xs text-slate-500">
            Live Gamma: {simState.metrics[simState.metrics.length - 1]?.gamma.toFixed(2) || '0.00'} Hz
          </div>
        </section>
      </div>

      <div className="min-h-[480px] h-full flex flex-col gap-2 p-2">
        <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1">
          <button type="button" onClick={() => setChatMode('local')} aria-pressed={chatMode === 'local'} className={`rounded-md px-2 py-2 text-[10px] font-bold uppercase tracking-wider ${chatMode === 'local' ? 'bg-slate-800 text-cyan-300' : 'text-slate-500 hover:text-slate-300'}`}>
            Local chat
          </button>
          <button type="button" onClick={() => setChatMode('ara')} aria-pressed={chatMode === 'ara'} className={`rounded-md px-2 py-2 text-[10px] font-bold uppercase tracking-wider ${chatMode === 'ara' ? 'bg-cyan-950 text-cyan-300' : 'text-slate-500 hover:text-slate-300'}`}>
            ARA backend
          </button>
        </div>
        <div className="flex-1 min-h-0">
          {chatMode === 'local' ? <ChatInterface simState={simState} /> : <AraChatPanel />}
        </div>
      </div>
    </div>
  );
};

export default MirrorMe;
