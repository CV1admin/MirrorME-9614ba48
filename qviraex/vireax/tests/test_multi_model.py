from __future__ import annotations

import unittest

from qviraex.vireax.adapters import AdapterEnvelope, AdapterResult, AdapterSpec, StaticAdapter
from qviraex.vireax.multi_model import converse
from qviraex.vireax.router import ModelRouter


class RecordingAdapter(StaticAdapter):
    def __init__(self, spec: AdapterSpec, response: str) -> None:
        super().__init__(spec)
        self.response = response
        self.prompts: list[str] = []

    def respond(self, envelope: AdapterEnvelope) -> AdapterResult:
        self.prompts.append(envelope.prompt)
        return AdapterResult(
            model=self.spec.model,
            provider=self.spec.provider,
            role=envelope.role,
            output=self.response,
            confidence=0.0,
            metadata={"confidence_is_calibrated": False},
        )


class MultiModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ModelRouter()
        self.alpha = RecordingAdapter(AdapterSpec("alpha", "test", "analyst"), "Alpha challenges the claim.")
        self.beta = RecordingAdapter(AdapterSpec("beta", "test", "critic"), "Beta identifies an uncertainty.")
        self.router.register(self.alpha)
        self.router.register(self.beta)

    def test_two_models_exchange_prior_contributions_with_bounded_rounds(self) -> None:
        result = converse(
            self.router,
            task="Evaluate a sample claim.",
            model_names=["alpha", "beta"],
            max_rounds=2,
            session_id="session-test",
            task_id="task-test",
        )
        self.assertEqual(result.status, "completed_unverified")
        self.assertEqual(len(result.turns), 4)
        self.assertIn("Alpha challenges the claim.", self.beta.prompts[0])
        self.assertIn("Beta identifies an uncertainty.", self.alpha.prompts[1])
        self.assertTrue(result.audit.verify())
        self.assertEqual(result.turns[0].output_sha256[:7], "sha256:")

    def test_requires_two_models(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            converse(self.router, task="x", model_names=["alpha"])

    def test_round_limit_is_hard_capped(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 3"):
            converse(self.router, task="x", model_names=["alpha", "beta"], max_rounds=4)

    def test_duplicate_model_names_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            converse(self.router, task="x", model_names=["alpha", "alpha"])

    def test_audit_does_not_store_raw_task_or_model_output(self) -> None:
        result = converse(
            self.router,
            task="PRIVATE TASK CONTENT",
            model_names=["alpha", "beta"],
            max_rounds=1,
        )
        serialized = repr(result.audit.records)
        self.assertNotIn("PRIVATE TASK CONTENT", serialized)
        self.assertNotIn("Alpha challenges the claim.", serialized)

    def test_unregistered_model_fails_closed(self) -> None:
        with self.assertRaisesRegex(KeyError, "not registered"):
            converse(self.router, task="x", model_names=["alpha", "missing"], max_rounds=1)


if __name__ == "__main__":
    unittest.main()
