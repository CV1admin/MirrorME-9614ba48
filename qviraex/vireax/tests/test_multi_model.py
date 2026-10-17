from __future__ import annotations

import unittest
from dataclasses import replace

from qviraex.vireax.adapters import AdapterEnvelope, AdapterResult, AdapterSpec, StaticAdapter
from qviraex.vireax.multi_model import CRITIC_LENSES, converse, verify_conversation_result
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


class RoundTaggedAdapter(RecordingAdapter):
    """Returns a unique, round-tagged output so leakage between turns is detectable."""

    def __init__(self, spec: AdapterSpec) -> None:
        super().__init__(spec, response="")
        self.roles: list[str] = []

    def respond(self, envelope: AdapterEnvelope) -> AdapterResult:
        self.roles.append(envelope.role)
        self.response = f"OUTPUT<{self.spec.model}:round-{envelope.metadata['round_number']}>"
        return super().respond(envelope)


class FirstRoundIndependenceTests(unittest.TestCase):
    """Audit finding F-01: initial analyses must not see peer outputs."""

    def setUp(self) -> None:
        self.router = ModelRouter()
        self.adapters = [RoundTaggedAdapter(AdapterSpec(name, "test", "analyst")) for name in ("alpha", "beta", "gamma")]
        for adapter in self.adapters:
            self.router.register(adapter)

    def _run(self, max_rounds: int):
        return converse(
            self.router,
            task="Evaluate a sample claim.",
            model_names=[adapter.spec.model for adapter in self.adapters],
            max_rounds=max_rounds,
            session_id="session-test",
            task_id="task-test",
        )

    def test_no_first_round_prompt_contains_any_model_response(self) -> None:
        result = self._run(max_rounds=2)
        first_round_prompts = [adapter.prompts[0] for adapter in self.adapters]
        for turn in result.turns:
            for prompt in first_round_prompts:
                self.assertNotIn(turn.output, prompt)
        for prompt in first_round_prompts:
            self.assertNotIn("Prior contributions", prompt)

    def test_every_model_receives_an_identical_first_round_prompt(self) -> None:
        self._run(max_rounds=1)
        first_round_prompts = {adapter.prompts[0] for adapter in self.adapters}
        self.assertEqual(len(first_round_prompts), 1)

    def test_review_rounds_see_all_prior_rounds_but_not_same_round_peers(self) -> None:
        self._run(max_rounds=3)
        for round_index, round_number in ((1, 2), (2, 3)):
            prompts = {adapter.prompts[round_index] for adapter in self.adapters}
            self.assertEqual(len(prompts), 1, f"round {round_number} prompts differ between models")
            prompt = prompts.pop()
            for adapter in self.adapters:
                for earlier in range(1, round_number):
                    self.assertIn(f"OUTPUT<{adapter.spec.model}:round-{earlier}>", prompt)
                self.assertNotIn(f"OUTPUT<{adapter.spec.model}:round-{round_number}>", prompt)

    def test_roles_follow_round_not_dispatch_order(self) -> None:
        result = self._run(max_rounds=2)
        for adapter in self.adapters:
            self.assertEqual(adapter.roles, ["independent_analyst", "critical_reviewer"])
        self.assertEqual(
            [turn.role for turn in result.turns if turn.round_number == 1],
            ["independent_analyst"] * len(self.adapters),
        )
        self.assertTrue(verify_conversation_result(result))


class CriticPanelTests(unittest.TestCase):
    """Specialised critic lenses in review rounds, plus an optional synthesis turn."""

    def setUp(self) -> None:
        self.router = ModelRouter()
        self.adapters = [RoundTaggedAdapter(AdapterSpec(name, "test", "analyst")) for name in ("alpha", "beta", "gamma")]
        for adapter in self.adapters:
            self.router.register(adapter)
        self.names = [adapter.spec.model for adapter in self.adapters]

    def run_panel(self, **kwargs):
        options = {"max_rounds": 2, "critic_lenses": ["math", "logic", "adversary"]}
        options.update(kwargs)
        return converse(self.router, task="Evaluate a sample claim.", model_names=self.names, **options)

    def test_review_round_gives_each_model_a_different_lens(self) -> None:
        result = self.run_panel()
        round_two = [turn.role for turn in result.turns if turn.round_number == 2]
        self.assertEqual(round_two, ["critic:math", "critic:logic", "critic:adversary"])
        for adapter, lens in zip(self.adapters, ["math", "logic", "adversary"]):
            self.assertIn(CRITIC_LENSES[lens], adapter.prompts[1])
            for other in set(CRITIC_LENSES) - {lens}:
                self.assertNotIn(CRITIC_LENSES[other], adapter.prompts[1])
        self.assertTrue(verify_conversation_result(result))

    def test_lenses_rotate_between_review_rounds(self) -> None:
        result = self.run_panel(max_rounds=3)
        by_round = {
            r: [turn.role for turn in result.turns if turn.round_number == r] for r in (2, 3)
        }
        self.assertEqual(by_round[2], ["critic:math", "critic:logic", "critic:adversary"])
        self.assertEqual(by_round[3], ["critic:logic", "critic:adversary", "critic:math"])

    def test_first_round_stays_independent_and_lens_free(self) -> None:
        self.run_panel()
        for adapter in self.adapters:
            self.assertEqual(adapter.roles[0], "independent_analyst")
            for text in CRITIC_LENSES.values():
                self.assertNotIn(text, adapter.prompts[0])
            self.assertNotIn("Prior contributions", adapter.prompts[0])

    def test_fewer_lenses_than_models_cycle(self) -> None:
        result = self.run_panel(critic_lenses=["adversary"])
        self.assertEqual(
            [turn.role for turn in result.turns if turn.round_number == 2],
            ["critic:adversary"] * 3,
        )

    def test_synthesis_runs_once_after_all_rounds_and_sees_everything(self) -> None:
        result = self.run_panel(synthesis_model="beta")
        self.assertEqual(len(result.turns), 7)
        final = result.turns[-1]
        self.assertEqual((final.model, final.role, final.round_number), ("beta", "synthesis", 3))
        synthesis_prompt = self.adapters[1].prompts[-1]
        self.assertIn("SYNTHESIS step", synthesis_prompt)
        self.assertIn("without settling it by majority vote", synthesis_prompt)
        for turn in result.turns[:-1]:
            self.assertIn(turn.output, synthesis_prompt)
        self.assertEqual(len(self.adapters[0].prompts), 2)
        self.assertEqual(len(self.adapters[2].prompts), 2)
        self.assertTrue(verify_conversation_result(result, expected_head_hash=result.audit.head_hash))

    def test_synthesis_without_lenses_keeps_plain_reviewers(self) -> None:
        result = converse(
            self.router, task="x", model_names=self.names, max_rounds=2, synthesis_model="alpha",
        )
        self.assertEqual(
            [turn.role for turn in result.turns],
            ["independent_analyst"] * 3 + ["critical_reviewer"] * 3 + ["synthesis"],
        )

    def test_default_behaviour_is_unchanged(self) -> None:
        result = converse(self.router, task="x", model_names=self.names, max_rounds=2)
        self.assertEqual(
            [turn.role for turn in result.turns],
            ["independent_analyst"] * 3 + ["critical_reviewer"] * 3,
        )

    def test_invalid_panel_options_fail_before_any_call(self) -> None:
        cases = [
            ({"critic_lenses": ["physics"]}, "subset of"),
            ({"critic_lenses": []}, "subset of"),
            ({"critic_lenses": ["math", "math"]}, "unique"),
            ({"critic_lenses": "math"}, "sequence of lens names"),
            ({"critic_lenses": ["math"], "max_rounds": 1}, "at least 2"),
            ({"synthesis_model": "delta"}, "one of model_names"),
        ]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, message):
                    self.run_panel(**kwargs)
        for adapter in self.adapters:
            self.assertEqual(adapter.prompts, [])

    def test_adapter_returning_a_different_role_is_rejected(self) -> None:
        class RoleSwapper(RecordingAdapter):
            def respond(self, envelope):
                result = super().respond(envelope)
                return replace(result, role="synthesis")

        router = ModelRouter()
        router.register(RoleSwapper(AdapterSpec("alpha", "test", "analyst"), "a"))
        router.register(RecordingAdapter(AdapterSpec("beta", "test", "analyst"), "b"))
        with self.assertRaisesRegex(ValueError, "returned role"):
            converse(router, task="x", model_names=["alpha", "beta"], max_rounds=1)

    def test_audit_records_panel_configuration(self) -> None:
        result = self.run_panel(synthesis_model="gamma")
        started = result.audit.records[0].payload
        self.assertEqual(started["critic_lenses"], ["math", "logic", "adversary"])
        self.assertEqual(started["synthesis_model"], "gamma")


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
        self.assertNotIn("Alpha challenges the claim.", self.beta.prompts[0])
        self.assertIn("Alpha challenges the claim.", self.beta.prompts[1])
        self.assertIn("Beta identifies an uncertainty.", self.alpha.prompts[1])
        self.assertTrue(result.audit.verify())
        self.assertEqual(result.turns[0].output_sha256[:7], "sha256:")
        self.assertTrue(verify_conversation_result(result, expected_head_hash=result.audit.head_hash))
        self.assertFalse(verify_conversation_result(result, expected_head_hash="sha256:" + "0" * 64))

    def test_transcript_output_tampering_is_detected(self) -> None:
        result = converse(
            self.router,
            task="Evaluate a sample claim.",
            model_names=["alpha", "beta"],
            max_rounds=1,
        )
        tampered_turn = replace(result.turns[0], output="forged response")
        tampered_result = replace(result, turns=(tampered_turn, *result.turns[1:]))
        self.assertFalse(verify_conversation_result(tampered_result))

    def test_public_record_snapshot_cannot_mutate_ledger(self) -> None:
        result = converse(
            self.router,
            task="Evaluate a sample claim.",
            model_names=["alpha", "beta"],
            max_rounds=1,
        )
        snapshot = result.audit.records
        snapshot[1].payload["model"] = "tampered"
        self.assertTrue(result.audit.verify())
        self.assertTrue(verify_conversation_result(result))

    def test_internal_payload_tampering_is_detected(self) -> None:
        result = converse(
            self.router,
            task="Evaluate a sample claim.",
            model_names=["alpha", "beta"],
            max_rounds=1,
        )
        result.audit._records[1].payload["model"] = "tampered"
        self.assertFalse(result.audit.verify())
        self.assertFalse(verify_conversation_result(result))

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

    def test_unregistered_model_fails_before_any_provider_call(self) -> None:
        with self.assertRaisesRegex(KeyError, "adapters not registered"):
            converse(self.router, task="x", model_names=["alpha", "missing"], max_rounds=1)
        self.assertEqual(self.alpha.prompts, [])
        self.assertEqual(self.beta.prompts, [])

    def test_model_names_string_rejected_as_not_a_sequence_of_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "sequence of model-name strings"):
            converse(self.router, task="x", model_names="alpha")

    def test_empty_or_non_string_model_names_rejected(self) -> None:
        for names in (["alpha", ""], ["alpha", None]):
            with self.subTest(names=names):
                with self.assertRaisesRegex(ValueError, "only non-empty strings"):
                    converse(self.router, task="x", model_names=names)

    def test_model_fanout_is_bounded(self) -> None:
        names = [f"model-{index}" for index in range(9)]
        with self.assertRaisesRegex(ValueError, "cannot contain more than 8 models"):
            converse(self.router, task="x", model_names=names)

    def test_task_size_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "task exceeds configured size limit"):
            converse(self.router, task="12345", model_names=["alpha", "beta"], max_task_chars=4)

    def test_output_limit_has_a_hard_upper_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 100,000"):
            converse(self.router, task="x", model_names=["alpha", "beta"], max_output_chars=100_001)


if __name__ == "__main__":
    unittest.main()
