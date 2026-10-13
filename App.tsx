import React, { useState, useEffect, useCallback } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import MirrorMe from './pages/MirrorMe';
import ThinLineTheory from './pages/ThinLineTheory';
import CivilisationDashboard from './pages/CivilisationDashboard';
import OiiidsOperationsDashboard from './pages/OiiidsOperationsDashboard';
import SystemMap from './pages/SystemMap';
import MKultraV04 from './pages/MKultraV04';
import Settings from './pages/Settings';
import { SimulationState, GateStatus, ContradictionEvent } from './types';
import { createBrainNodes, createMetricFrame, isHealthyFrame } from './simulation/SimulationEngine';

const INITIAL_NODES = createBrainNodes();

const MOCK_CONTRADICTION: ContradictionEvent = {
  id: 'trap-resolution-swan-001',
  event: "contradiction_trap_resolution",
  timestamp: 0,
  inputs: {
    "A": "All swans are white.",
    "B": "A black swan exists."
  },
  formalization: {
    "A": "forall x (Swan(x) -> White(x))",
    "B": "exists x (Swan(x) and not White(x))"
  },
  result: {
    "classification": "INCONSISTENT_UNDER_CLASSICAL_LOGIC",
    "explanation": "B provides a counterexample to A."
  },
  repairs_minimal: [
    { type: "revise_axiom", change: "A -> 'Most swans are white'", cost: "low", notes: "Preserves classical logic." },
    { type: "defeasible_default", change: "A becomes a default rule", cost: "medium", notes: "Non-monotonic logic." },
    { type: "paraconsistent_logic", change: "Keep A and B; prevent explosion", cost: "medium-high", notes: "Logic layer upgrade." }
  ],
  assumptions: ["Classical FOL"],
  constraints_checked: ["Non-contradiction", "Minimal-change repairs"],
  violations: ["Non-contradiction violated"],
  confidence: 1.0,
  refs: ["MKone_LogicGate_Audit/ContradictionTrap"]
};

const App: React.FC = () => {
  const [simState, setSimState] = useState<SimulationState>({
    isRunning: false,
    gateStatus: GateStatus.NOGO,
    consecutiveGoFrames: 0,
    consecutiveNoGoFrames: 0,
    currentFrame: 0,
    metrics: [],
    nodes: INITIAL_NODES,
  });

  const updateSim = useCallback(() => {
    if (!simState.isRunning) return;

    setSimState((prev) => {
      const t = prev.currentFrame;
      const newFrame = createMetricFrame(t);

      let activeContradiction = prev.activeContradiction;
      if (t > 0 && t % 300 === 0 && !activeContradiction) {
        activeContradiction = { ...MOCK_CONTRADICTION, timestamp: t };
      } else if (t % 500 === 0) {
        activeContradiction = undefined;
      }

      const isHealthy = isHealthyFrame(newFrame);

      let nextGate = prev.gateStatus;
      let nextGoFrames = prev.consecutiveGoFrames;
      let nextNoGoFrames = prev.consecutiveNoGoFrames;

      if (isHealthy) {
        nextGoFrames++;
        nextNoGoFrames = 0;
        if (nextGoFrames >= 5) nextGate = GateStatus.GO;
      } else {
        nextNoGoFrames++;
        nextGoFrames = 0;
        if (nextNoGoFrames >= 2) nextGate = GateStatus.NOGO;
        else if (nextGate === GateStatus.GO) nextGate = GateStatus.STABILIZING;
      }

      return {
        ...prev,
        gateStatus: nextGate,
        consecutiveGoFrames: nextGoFrames,
        consecutiveNoGoFrames: nextNoGoFrames,
        currentFrame: t + 1,
        metrics: [...prev.metrics.slice(-99), newFrame],
        activeContradiction
      };
    });
  }, [simState.isRunning]);

  useEffect(() => {
    const interval = setInterval(updateSim, 50);
    return () => clearInterval(interval);
  }, [updateSim]);

  const toggleSimulation = () => {
    setSimState(prev => ({
      ...prev,
      isRunning: !prev.isRunning,
      gateStatus: prev.isRunning ? GateStatus.NOGO : GateStatus.STABILIZING,
      consecutiveGoFrames: 0,
      consecutiveNoGoFrames: 0,
      activeContradiction: undefined
    }));
  };

  return (
    <HashRouter>
      <Layout simState={simState} toggleSimulation={toggleSimulation}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<CivilisationDashboard />} />
          <Route path="/civilisation-dashboard" element={<CivilisationDashboard />} />
          <Route path="/system-map" element={<SystemMap />} />
          <Route path="/oiiids-operations" element={<OiiidsOperationsDashboard />} />
          <Route path="/mirrorme" element={<MirrorMe simState={simState} />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/mkultra-v04" element={<MKultraV04 />} />
          <Route path="/thin-line-theory" element={<ThinLineTheory />} />
        </Routes>
      </Layout>
    </HashRouter>
  );
};

export default App;
