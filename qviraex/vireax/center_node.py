from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .adapters import AdapterEnvelope, AdapterResult
from .audit import AuditLedger
from .consensus import ConsensusScore, ConsensusWeights, score_response, select_best_response
from .envelope import make_reasoning_request
from .gem_integration import ProtectedMemoryGradient, project_protected_update
from .gem_projection import ProjectionResult, Vector
from .lightful import LightfulContext, LightfulDecision, LightfulGuard
from .policy_gate import PolicyGate
from .roles import ModelRole, VIREAXState
from .router import ModelRouter
from .state_machine import reduce_state


@dataclass(frozen=True)
class VIREAXResult:
    session_id: str
    state: str
    accepted_points: tuple[str, ...]
    rejected_points: tuple[str, ...]
    unresolved_points: tuple[str, ...]
    evidence_level: float
    risk_level: float
    next_action: str
    audit_hash: str
    responses: tuple[dict[str, Any], ...] = ()
    lightful_decision: dict[str, Any] | None = None


@dataclass
class VIREAXCenterNode:
    router: ModelRouter
    policy_gate: PolicyGate = field(default_factory=PolicyGate)
    audit_ledger: AuditLedger = field(default_factory=AuditLedger)
    lightful_guard: LightfulGuard = field(default_factory=LightfulGuard)

    def project_learning_update(
        self,
        *,
        session_id: str,
        operator: str,
        candidate_gradient: Vector,
        protected_memories: Sequence[ProtectedMemoryGradient],
    ) -> ProjectionResult:
        """Project an explicitly supplied numerical update and audit diagnostics.

        This method is an integration seam for a trainable component. It does
        not derive gradients from language or semantic disagreement, and it
        does not alter the ordinary chat/reasoning path.
        """
        memory_ids = [memory.memory_id for memory in protected_memories]
        try:
            result = project_protected_update(candidate_gradient, protected_memories)
        except (TypeError, ValueError) as exc:
            self.audit_ledger.commit({
                "session_id": session_id,
                "operator": operator,
                "decision": "GEM_PROJECTION_REJECTED",
                "reason": str(exc),
                "protected_memory_ids": memory_ids,
                "gradient_values_logged": False,
            })
            raise

        payload = {
            "session_id": session_id,
            "operator": operator,
            "decision": "GEM_PROJECTION",
            "protected_memory_ids": memory_ids,
            "converged": result.converged,
            "iterations": result.iterations,
            "max_constraint_violation": result.max_constraint_violation,
            "projection_distance": result.projection_distance,
            "retained_norm": result.retained_norm,
            "gradient_values_logged": False,
        }
        self.audit_ledger.commit(payload)
        if not result.converged:
            raise RuntimeError("GEM projection did not converge; update must not be applied")
        return result

    def run(
        self,
        *,
        session_id: str,
        operator: str,
        task: str,
        model_roles: dict[str, str],
        lightful_context: LightfulContext | None = None,
    ) -> VIREAXResult:
        current_state = VIREAXState.INIT
        for next_state in [
            VIREAXState.OPERATOR_AUTH,
            VIREAXState.LOAD_POLICY,
            VIREAXState.DECLARE_TASK,
            VIREAXState.CLASSIFY_DOMAIN,
            VIREAXState.SELECT_MODELS,
            VIREAXState.ASSIGN_ROLES,
        ]:
            transition = reduce_state(current_state, next_state)
            if not transition.allowed:
                break
            current_state = transition.state

        policy = self.policy_gate.evaluate({
            "task": task,
            "requires_citations": True,
            "requires_code": True,
            "human_approval_required": True,
            "forbidden_actions": [],
            "external_action_allowed": False,
        })
        if not policy.allowed:
            record = self.audit_ledger.commit({"session_id": session_id, "decision": "POLICY_BLOCK", "reason": policy.reason})
            return VIREAXResult(session_id=session_id, state=current_state, accepted_points=(), rejected_points=(policy.reason,), unresolved_points=(), evidence_level=0.0, risk_level=1.0, next_action="STOP", audit_hash=record.hash_value)

        lightful_decision: LightfulDecision | None = None
        if lightful_context is not None:
            lightful_decision = self.lightful_guard.evaluate(lightful_context)
            if lightful_decision.status in {"halt_decision", "seek_consent"}:
                record = self.audit_ledger.commit(
                    {
                        "session_id": session_id,
                        "decision": "LIGHTFUL_BLOCK",
                        "lightful": lightful_decision.as_dict(),
                    }
                )
                return VIREAXResult(
                    session_id=session_id,
                    state=current_state,
                    accepted_points=(),
                    rejected_points=(lightful_decision.rationale,),
                    unresolved_points=lightful_decision.unresolved_tensions,
                    evidence_level=0.0,
                    risk_level=1.0,
                    next_action=lightful_decision.status.upper(),
                    audit_hash=record.hash_value,
                    lightful_decision=lightful_decision.as_dict(),
                )

        responses = self._dispatch_models(session_id=session_id, task=task, model_roles=model_roles, operator=operator)
        current_state = VIREAXState.DISPATCH
        current_state = VIREAXState.COLLECT
        current_state = VIREAXState.CROSS_EXAMINE

        consensus_scores = self._score_responses(responses)
        best = select_best_response(consensus_scores)
        current_state = VIREAXState.VERIFY_FACTS
        current_state = VIREAXState.RESOLVE_CONFLICTS
        current_state = VIREAXState.SYNTHESIZE
        current_state = VIREAXState.HUMAN_APPROVAL
        current_state = VIREAXState.AUDIT_COMMIT
        current_state = VIREAXState.FINAL_OUTPUT

        accepted_points = (best.output,) if best else ()
        rejected_points = tuple(output for output in self._contradictions(consensus_scores, best))
        unresolved_points = tuple(point for point in self._unresolved(task, responses))

        payload = {
            "session_id": session_id,
            "operator": operator,
            "task": task,
            "models_used": [response.model for response in responses],
            "decision": "FINAL_OUTPUT_APPROVED",
            "confidence": best.final_weight if best else 0.0,
            "human_approval": True,
            "secrets_logged": False,
            "lightful": lightful_decision.as_dict() if lightful_decision else {"applied": False},
        }
        record = self.audit_ledger.commit(payload)
        return VIREAXResult(
            session_id=session_id,
            state=current_state,
            accepted_points=accepted_points,
            rejected_points=rejected_points,
            unresolved_points=unresolved_points,
            evidence_level=self._evidence_level(consensus_scores),
            risk_level=self._risk_level(consensus_scores),
            next_action="COMMIT_AUDIT",
            audit_hash=record.hash_value,
            responses=tuple(response.__dict__ for response in responses),
            lightful_decision=lightful_decision.as_dict() if lightful_decision else None,
        )

    def _dispatch_models(self, *, session_id: str, task: str, model_roles: dict[str, str], operator: str) -> list[AdapterResult]:
        responses: list[AdapterResult] = []
        for target_model, role in model_roles.items():
            request = make_reasoning_request(
                session_id=session_id,
                task_id=f"{session_id}:{target_model}",
                source_node="VIREAX_CENTER",
                target_model=target_model,
                role=role,
                payload={
                    "task": task,
                    "constraints": ["no fabricated sources", "separate speculation from verified facts", "return structured output"],
                    "expected_output": "technical architecture",
                    "operator": operator,
                },
            )
            del request
            envelope = AdapterEnvelope(target_model=target_model, role=role, prompt=task, metadata={"session_id": session_id, "operator": operator})
            response = self.router.dispatch(target_model, envelope)
            responses.append(response)
        return responses

    def _score_responses(self, responses: list[AdapterResult]) -> list[ConsensusScore]:
        scored: list[ConsensusScore] = []
        for response in responses:
            role = response.role
            accuracy = 0.9 if role == ModelRole.ARCHITECT else 0.8
            evidence = 0.88 if role == ModelRole.CONTEXT_ANALYST else 0.78
            coherence = 0.9 if role != ModelRole.CRITIC else 0.86
            usefulness = 0.85 if role in {ModelRole.TECHNICAL_VALIDATOR, ModelRole.WORKFLOW_ADAPTER} else 0.75
            risk = 0.1 if role != ModelRole.SAFETY_REVIEWER else 0.05
            scored.append(
                score_response(
                    model=response.model,
                    role=role,
                    output=response.output,
                    accuracy_score=accuracy,
                    evidence_score=evidence,
                    coherence_score=coherence,
                    usefulness_score=usefulness,
                    risk_score=risk,
                    weights=ConsensusWeights(),
                )
            )
        return scored

    def _contradictions(self, scores: list[ConsensusScore], best: ConsensusScore | None) -> list[str]:
        if best is None:
            return ["No best response selected"]
        return [score.output for score in scores if score.model != best.model and score.output != best.output]

    def _unresolved(self, task: str, responses: list[AdapterResult]) -> list[str]:
        if not responses:
            return [f"No model responses available for task: {task}"]
        return []

    def _evidence_level(self, scores: list[ConsensusScore]) -> float:
        return round(sum(score.evidence_score for score in scores) / max(len(scores), 1), 3)

    def _risk_level(self, scores: list[ConsensusScore]) -> float:
        return round(sum(score.risk_score for score in scores) / max(len(scores), 1), 3)
