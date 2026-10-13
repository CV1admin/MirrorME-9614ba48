from __future__ import annotations

import unittest

from qviraex.vireax.ara_adapter import create_ara_adapter_from_env, register_ara_adapter
from qviraex.vireax.router import ModelRouter


class AraAdapterConfigurationTests(unittest.TestCase):
    def test_requires_explicit_endpoint_and_model_id(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "VIREAX_ARA_ENDPOINT"):
            create_ara_adapter_from_env({})
        with self.assertRaisesRegex(RuntimeError, "VIREAX_ARA_MODEL"):
            create_ara_adapter_from_env({
                "VIREAX_ARA_ENDPOINT": "http://127.0.0.1:8000/v1/chat/completions",
            })

    def test_rejects_supplied_github_profile_as_inference_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "GitHub webpage"):
            create_ara_adapter_from_env({
                "VIREAX_ARA_ENDPOINT": "https://github.com/Geminatrix?tab=repositories",
                "VIREAX_ARA_MODEL": "unknown",
            })

    def test_accepts_explicit_local_openai_compatible_runtime(self) -> None:
        adapter = create_ara_adapter_from_env({
            "VIREAX_ARA_ENDPOINT": "http://127.0.0.1:8000/v1/chat/completions",
            "VIREAX_ARA_MODEL": "local-dane-model",
        })
        self.assertEqual(adapter.spec.model, "ARA")
        self.assertEqual(adapter.spec.provider, "Dane Model")
        self.assertEqual(adapter.api_model, "local-dane-model")
        self.assertIsNone(adapter.api_key_env)

    def test_registers_ara_in_router_without_network_request(self) -> None:
        router = ModelRouter()
        adapter = register_ara_adapter(router, {
            "VIREAX_ARA_ENDPOINT": "http://127.0.0.1:8000/v1/chat/completions",
            "VIREAX_ARA_MODEL": "local-dane-model",
        })
        self.assertIs(router.registry["ARA"], adapter)
        self.assertEqual(router.registry["ARA"].spec.provider, "Dane Model")

    def test_remote_endpoint_requires_explicit_secret_configuration(self) -> None:
        base = {
            "VIREAX_ARA_ENDPOINT": "https://models.example/v1/chat/completions",
            "VIREAX_ARA_MODEL": "dane-model",
        }
        with self.assertRaisesRegex(RuntimeError, "VIREAX_ARA_API_KEY_ENV"):
            create_ara_adapter_from_env(base)

    def test_remote_endpoint_requires_secret_value(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "credential variable"):
            create_ara_adapter_from_env({
                "VIREAX_ARA_ENDPOINT": "https://models.example/v1/chat/completions",
                "VIREAX_ARA_MODEL": "dane-model",
                "VIREAX_ARA_API_KEY_ENV": "ARA_TEST_SECRET",
            })

    def test_remote_endpoint_uses_secret_from_environment_mapping(self) -> None:
        adapter = create_ara_adapter_from_env({
            "VIREAX_ARA_ENDPOINT": "https://models.example/v1/chat/completions",
            "VIREAX_ARA_MODEL": "dane-model",
            "VIREAX_ARA_API_KEY_ENV": "ARA_TEST_SECRET",
            "ARA_TEST_SECRET": "test-only-secret",
        })
        self.assertEqual(adapter.api_key_env, "ARA_TEST_SECRET")
        self.assertNotEqual(adapter.api_key_env, "test-only-secret")


if __name__ == "__main__":
    unittest.main()
