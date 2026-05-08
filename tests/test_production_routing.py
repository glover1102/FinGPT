import unittest

from core.config.settings import Settings
from core.utils.model_capabilities import model_capability_dict
from pipelines.infer.runner_factory import resolve_model_name


class ProductionRoutingTests(unittest.TestCase):
    def test_primary_aliases_resolve_to_primary_model(self):
        settings = Settings()
        for alias in ("qwen", "mistral", "ollama", "primary", "fingpt", "llama-2", ""):
            self.assertEqual(resolve_model_name(alias, settings), settings.primary_model)

    def test_fingpt_capability_profile_is_auxiliary_for_structured_reports(self):
        profile = model_capability_dict("fingpt", "qwen2.5:7b")
        self.assertFalse(profile["structured_output_support"])
        self.assertTrue(profile["gpu_required"])
        self.assertIn("final_report", profile["restricted_tasks"])

    def test_gemma4_route_resolves_without_fallback_enablement(self):
        settings = Settings(enable_experimental_fallback=False, gemma4_model="gemma4:e4b")
        self.assertEqual(resolve_model_name("gemma4", settings), "gemma4:e4b")

    def test_gemma4_capability_profile_is_explicit_experimental_option(self):
        profile = model_capability_dict("gemma4", "gemma4:e4b")
        self.assertTrue(profile["structured_output_support"])
        self.assertFalse(profile["gpu_required"])
        self.assertIn("single_name_research_comparison", profile["recommended_tasks"])
        self.assertNotIn("production_final_report", profile["restricted_tasks"])

    def test_gemma_route_requires_explicit_enablement(self):
        settings = Settings(enable_experimental_fallback=False)
        with self.assertRaises(ValueError):
            resolve_model_name("gemma", settings)

    def test_gemma_route_resolves_when_experiment_enabled(self):
        settings = Settings(enable_experimental_fallback=True, experimental_fallback_model="gemma4:e4b")
        self.assertEqual(resolve_model_name("gemma-experimental", settings), "gemma4:e4b")


if __name__ == "__main__":
    unittest.main()
