"""Explicitly enabled, read-only AI catalog checks; never generate tokens or spend inference credits."""
import os

import pytest

from papertrade.ai.budget import UsageBudget
from papertrade.ai.service import AIDisabled, make_provider
from papertrade.config import Settings
from papertrade.db import Database

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("PT_RUN_AI_INTEGRATION", "").lower() != "true",
    reason="Set PT_RUN_AI_INTEGRATION=true to call real provider model catalogs explicitly")]


@pytest.mark.parametrize("provider", ["groq", "hermes"])
def test_real_ai_provider_model_catalog_only(tmp_path, provider):
    configured = Settings()
    key = configured.groq_api_key if provider == "groq" else configured.hermes_api_key
    if not key.get_secret_value():
        pytest.skip(f"{provider} credentials missing")
    if provider == "hermes" and not configured.ai_allow_paid:
        pytest.skip("Hermes paid/API access not explicitly authorized")
    configured = configured.model_copy(update={"ai_provider": provider,
        "database_url": f"sqlite:///{tmp_path / 'integration-usage.db'}", "state_dir": tmp_path})
    db = Database(configured)
    db.initialize()
    try:
        try:
            adapter = make_provider(configured, UsageBudget(db), discovery=True)
        except AIDisabled as exc:
            pytest.skip(str(exc))
        models = adapter.get_models(refresh=True)
        assert models and all(isinstance(model.get("id"), str) for model in models)
        assert adapter.get_usage_metrics()["total_tokens"] == 0
        # This certifies a read-only catalog endpoint only, never chat compatibility or recommendation quality.
        adapter.close()
    finally:
        db.engine.dispose()
