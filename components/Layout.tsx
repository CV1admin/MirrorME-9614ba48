
import React from 'react';
import Sidebar, { MobileNav } from './Sidebar';
import { SimulationState, GateStatus } from '../types';

interface LayoutProps {
  children: React.ReactNode;
  simState: SimulationState;
  toggleSimulation: () => void;
}

const Layout: React.FC<LayoutProps> = ({ children, simState, toggleSimulation }) => {
  const getGateColor = (status: GateStatus) => {
    switch (status) {
      case GateStatus.GO: return 'bg-green-500 text-green-950';
      case GateStatus.STABILIZING: return 'bg-yellow-500 text-yellow-950';
      case GateStatus.NOGO: return 'bg-red-500 text-red-50';
      default: return 'bg-slate-700 text-slate-200';
    }
  };

  const logicStatus = simState.activeContradiction 
    ? { label: 'INCONSISTENT', color: 'text-rose-500' }
    : { label: 'CONSISTENT (FOL)', color: 'text-emerald-500' };

  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-200 overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-slate-800 flex items-center justify-between gap-3 px-3 md:px-6 bg-slate-900/50 backdrop-blur-md z-50">
          <div className="flex items-center gap-4 min-w-0">
            <h1 className="font-bold tracking-tight text-sm md:text-lg text-cyan-400 truncate">Civilisation.One <span className="text-slate-500 font-normal">/</span> Unified Intelligence Console</h1>
            <div className="hidden md:block h-4 w-[1px] bg-slate-700" />
            <div className="hidden md:flex items-center gap-3">
              <span className="text-[10px] uppercase font-bold tracking-widest text-slate-500">Gate</span>
              <div className={`px-2 py-0.5 rounded text-[10px] font-black tracking-tighter ${getGateColor(simState.gateStatus)}`}>
                {simState.gateStatus}
              </div>
            </div>
            <div className="hidden md:block h-4 w-[1px] bg-slate-700" />
            <div className="hidden md:flex flex-col">
              <span className="text-[8px] uppercase font-bold text-slate-600">Logic Layer</span>
              <span className={`text-[10px] font-black tracking-widest ${logicStatus.color}`}>{logicStatus.label}</span>
            </div>
          </div>
          
          <div className="flex items-center gap-3 md:gap-6 shrink-0">
            <div className="hidden md:flex flex-col items-end">
               <span className="text-[8px] uppercase font-bold text-slate-600">Cognitive Velocity</span>
               <span className="text-xs mono text-cyan-500">
                {simState.metrics[simState.metrics.length-1]?.gamma.toFixed(2) || '0.00'} Hz
               </span>
            </div>
             <button 
              onClick={toggleSimulation}
              className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                simState.isRunning 
                ? 'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20' 
                : 'bg-cyan-500 text-slate-950 hover:bg-cyan-400'
              }`}
            >
              {simState.isRunning ? 'TERMINATE RUN' : 'INITIALIZE SIM'}
            </button>
            <div className="hidden md:block text-xs mono text-slate-500 bg-slate-800/50 px-2 py-1 rounded border border-slate-700">
              ID:{simState.currentFrame.toString().padStart(6, '0')}
            </div>
          </div>
        </header>
        <MobileNav />
        <div className="flex-1 relative overflow-auto">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;
