"""Tests for IBM watsonx.ai LLM provider integration.

Tests the watsonx integration path with mocks so everything
works correctly once a valid API key is provided.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestWatsonxClientFactory:
    """Test the _get_llm_client factory for watsonx provider."""

    @patch.dict("os.environ", {
        "LLM_PROVIDER": "watsonx",
        "WATSONX_API_KEY": "test-key-123",
        "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
        "WATSONX_PROJECT_ID": "test-project-id",
        "WATSONX_MODEL": "ibm/granite-3-8b-instruct",
    })
    @patch("ibm_watsonx_ai.foundation_models.ModelInference")
    @patch("ibm_watsonx_ai.Credentials")
    def test_watsonx_client_created(self, mock_creds, mock_model):
        from app import _get_llm_client
        mock_model_instance = MagicMock()
        mock_model.return_value = mock_model_instance

        client = _get_llm_client()

        mock_creds.assert_called_once_with(
            url="https://us-south.ml.cloud.ibm.com",
            api_key="test-key-123",
        )
        mock_model.assert_called_once()
        assert client is mock_model_instance
        assert client._watsonx_model is True

    @patch.dict("os.environ", {
        "LLM_PROVIDER": "watsonx",
        "WATSONX_API_KEY": "",
    })
    def test_watsonx_returns_none_without_key(self):
        from app import _get_llm_client
        client = _get_llm_client()
        assert client is None

    @patch.dict("os.environ", {"LLM_PROVIDER": "rule_based"})
    def test_rule_based_returns_none(self):
        from app import _get_llm_client
        client = _get_llm_client()
        assert client is None

    @patch.dict("os.environ", {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test",
    })
    @patch("openai.OpenAI")
    def test_openai_client_created(self, mock_openai_cls):
        from app import _get_llm_client
        mock_openai_cls.return_value = MagicMock()
        client = _get_llm_client()
        mock_openai_cls.assert_called_once_with(api_key="sk-test")
        assert client is not None


class TestWatsonxReasoning:
    """Test the watsonx reasoning path in compliance checker."""

    def test_reason_with_watsonx_compliant(self):
        from compliance_checker import _reason_with_watsonx

        mock_model = MagicMock()
        mock_model.generate_text.return_value = (
            "Judgment: compliant\n"
            "Explanation: The business process aligns with the stated obligations."
        )
        mock_model._watsonx_model = True

        result = _reason_with_watsonx(
            "Test compliance prompt with regulations...",
            mock_model,
        )
        assert result["judgment"] == "compliant"
        assert "aligns" in result["explanation"]
        mock_model.generate_text.assert_called_once()

    def test_reason_with_watsonx_non_compliant(self):
        from compliance_checker import _reason_with_watsonx

        mock_model = MagicMock()
        mock_model.generate_text.return_value = (
            "Judgment: non_compliant\n"
            "Explanation: The business process shares data without consent."
        )
        mock_model._watsonx_model = True

        result = _reason_with_watsonx(
            "Test prompt...",
            mock_model,
        )
        assert result["judgment"] == "non_compliant"
        assert "consent" in result["explanation"]

    def test_reason_with_watsonx_error_handling(self):
        from compliance_checker import _reason_with_watsonx

        mock_model = MagicMock()
        mock_model.generate_text.side_effect = Exception("Connection timeout")
        mock_model._watsonx_model = True

        result = _reason_with_watsonx("Test prompt...", mock_model)
        assert result["judgment"] == "undetermined"
        assert "watsonx error" in result["explanation"]

    def test_reason_with_llm_dispatches_to_watsonx(self):
        from compliance_checker import _reason_with_llm

        mock_model = MagicMock()
        mock_model._watsonx_model = True
        mock_model.generate_text.return_value = (
            "Judgment: undetermined\nExplanation: Not enough info."
        )

        result = _reason_with_llm("Test prompt...", mock_model)
        assert result["judgment"] == "undetermined"
        mock_model.generate_text.assert_called_once()

    def test_reason_with_llm_dispatches_to_openai(self):
        from compliance_checker import _reason_with_llm

        mock_client = MagicMock()
        # No _watsonx_model attribute
        del mock_client._watsonx_model
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="Judgment: compliant\nExplanation: All good."
            ))]
        )

        result = _reason_with_llm("Test prompt...", mock_client)
        assert result["judgment"] == "compliant"


class TestParseComplianceResponse:
    """Test the response parsing helper."""

    def test_parse_standard_response(self):
        from compliance_checker import _parse_compliance_response
        response = "Judgment: compliant\nExplanation: The process is compliant."
        result = _parse_compliance_response(response)
        assert result["judgment"] == "compliant"
        assert "compliant" in result["explanation"]

    def test_parse_non_compliant(self):
        from compliance_checker import _parse_compliance_response
        response = "Judgment: non_compliant\nExplanation: Violation found."
        result = _parse_compliance_response(response)
        assert result["judgment"] == "non_compliant"

    def test_parse_undetermined_default(self):
        from compliance_checker import _parse_compliance_response
        response = "I'm not sure about this one. More context needed."
        result = _parse_compliance_response(response)
        assert result["judgment"] == "undetermined"

    def test_parse_case_insensitive(self):
        from compliance_checker import _parse_compliance_response
        response = "judgment: COMPLIANT\nexplanation: All requirements met."
        result = _parse_compliance_response(response)
        assert result["judgment"] == "compliant"


class TestFullPipelineWithWatsonx:
    """Test the full compliance check pipeline with watsonx mock."""

    def test_end_to_end_with_watsonx(self):
        from compliance_checker import check_compliance

        mock_model = MagicMock()
        mock_model._watsonx_model = True
        mock_model.generate_text.return_value = (
            "Judgment: compliant\n"
            "Explanation: Security measures are in place."
        )

        regulation = "Organizations must use security measures to protect personal data."
        business = "We use industry-standard encryption to protect your data."

        results = check_compliance(
            business_text=business,
            regulation_text=regulation,
            llm_client=mock_model,
        )

        assert len(results) >= 1
        assert results[0]["result"] == "compliant"
        assert mock_model.generate_text.called

    def test_end_to_end_without_llm_falls_back(self):
        from compliance_checker import check_compliance

        regulation = "Organizations must use security measures to protect personal data."
        business = "We use industry-standard encryption to protect your data."

        results = check_compliance(
            business_text=business,
            regulation_text=regulation,
            llm_client=None,
        )

        assert len(results) >= 1
        assert results[0]["result"] in ("compliant", "non_compliant", "undetermined")
