"""LLM provider registry — add new providers here.

Each provider is a function that returns a client object (or None if not configured).
The compliance checker dispatches reasoning calls based on client attributes.

To add a new provider:
    1. Write a factory function that returns a client (or None)
    2. Write a reasoning function: (prompt: str, client) -> dict
    3. Register both below
"""

import os
import re
from typing import Optional, Protocol


class ReasoningFn(Protocol):
    def __call__(self, prompt: str, client) -> dict: ...


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, dict] = {}


def register_provider(name: str, factory, reasoning_fn: ReasoningFn, marker_attr: str):
    """
    Register an LLM provider.

    Args:
        name: Provider key (matches LLM_PROVIDER env var)
        factory: Callable that returns a client or None
        reasoning_fn: (prompt, client) -> {"judgment": ..., "explanation": ...}
        marker_attr: Attribute set on the client so the checker knows which provider it is
    """
    _PROVIDERS[name] = {
        "factory": factory,
        "reasoning_fn": reasoning_fn,
        "marker_attr": marker_attr,
    }


def get_llm_client():
    """Create an LLM client based on LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "rule_based").lower()
    if provider == "rule_based":
        return None
    entry = _PROVIDERS.get(provider)
    if not entry:
        return None
    return entry["factory"]()


def get_reasoning_fn(client) -> Optional[ReasoningFn]:
    """Find the reasoning function for a given client."""
    if client is None:
        return None
    for entry in _PROVIDERS.values():
        attr = entry["marker_attr"]
        val = getattr(client, attr, None)
        if val is True:
            return entry["reasoning_fn"]
    return None


def get_provider_status() -> dict:
    """Return current provider config status (for the /api/llm-status endpoint)."""
    provider = os.getenv("LLM_PROVIDER", "rule_based").lower()

    if provider == "rule_based":
        return {"provider": provider, "model": "heuristic", "status": "active"}

    if provider == "watsonx":
        model = os.getenv("WATSONX_MODEL", "ibm/granite-3-8b-instruct")
        has_key = bool(os.getenv("WATSONX_API_KEY"))
        has_project = bool(os.getenv("WATSONX_PROJECT_ID"))
        status = "active" if has_key else "no_key"
        if has_key and not has_project:
            status = "no_project"
        return {"provider": provider, "model": model, "status": status}

    if provider == "bedrock":
        model = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-6")
        has_access = bool(os.getenv("AWS_ACCESS_KEY_ID"))
        has_secret = bool(os.getenv("AWS_SECRET_ACCESS_KEY"))
        status = "active" if (has_access and has_secret) else "no_key"
        return {"provider": provider, "model": model, "status": status}

    if provider == "openai":
        model = os.getenv("OPENAI_MODEL", "gpt-4")
        status = "active" if os.getenv("OPENAI_API_KEY") else "no_key"
        return {"provider": provider, "model": model, "status": status}

    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3")
        return {"provider": provider, "model": model, "status": "active"}

    return {"provider": provider, "model": "unknown", "status": "unknown"}


# ===========================================================================
# Built-in providers
# ===========================================================================


# --- OpenAI ---

def _openai_factory():
    try:
        import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        client = openai.OpenAI(api_key=api_key)
        client._is_openai = True
        return client
    except ImportError:
        return None


def _openai_reason(prompt: str, client) -> dict:
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content
        return _parse_response(content)
    except Exception as e:
        return {"judgment": "undetermined", "explanation": f"OpenAI error: {e}"}


register_provider("openai", _openai_factory, _openai_reason, "_is_openai")


# --- IBM watsonx.ai ---

def _watsonx_factory():
    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        api_key = os.getenv("WATSONX_API_KEY")
        url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        project_id = os.getenv("WATSONX_PROJECT_ID")
        model_id = os.getenv("WATSONX_MODEL", "ibm/granite-3-8b-instruct")

        if not api_key:
            return None

        credentials = Credentials(url=url, api_key=api_key)
        model = ModelInference(
            model_id=model_id,
            credentials=credentials,
            project_id=project_id or None,
        )
        model._is_watsonx = True
        model._watsonx_model = True  # legacy compat for tests
        return model
    except (ImportError, Exception):
        return None


def _watsonx_reason(prompt: str, client) -> dict:
    try:
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
        from ibm_watsonx_ai.foundation_models.utils.enums import DecodingMethods

        params = {
            GenParams.DECODING_METHOD: DecodingMethods.GREEDY,
            GenParams.MAX_NEW_TOKENS: 500,
            GenParams.TEMPERATURE: 0.1,
            GenParams.STOP_SEQUENCES: ["\n\n\n"],
        }

        content = client.generate_text(prompt=prompt, params=params)
        return _parse_response(content)
    except Exception as e:
        return {"judgment": "undetermined", "explanation": f"watsonx error: {e}"}


register_provider("watsonx", _watsonx_factory, _watsonx_reason, "_is_watsonx")


# --- AWS Bedrock ---

def _bedrock_factory():
    try:
        import boto3

        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        region = os.getenv("AWS_REGION", "us-east-1")
        model_id = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-6")

        if not access_key or not secret_key:
            return None

        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client._is_bedrock = True
        client._bedrock_model = True  # legacy compat for tests
        client._bedrock_model_id = model_id
        return client
    except (ImportError, Exception):
        return None


def _bedrock_reason(prompt: str, client) -> dict:
    import json

    try:
        model_id = getattr(client, "_bedrock_model_id", "anthropic.claude-sonnet-4-6")
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        content = result["content"][0]["text"]
        return _parse_response(content)
    except Exception as e:
        return {"judgment": "undetermined", "explanation": f"Bedrock error: {e}"}


register_provider("bedrock", _bedrock_factory, _bedrock_reason, "_is_bedrock")


# ---------------------------------------------------------------------------
# Shared response parser
# ---------------------------------------------------------------------------

def _parse_response(content: str) -> dict:
    """Parse LLM response for judgment and explanation."""
    judgment = "undetermined"
    explanation = content

    match = re.search(
        r"Judgment:\s*(compliant|non_compliant|undetermined)",
        content, re.IGNORECASE,
    )
    if match:
        judgment = match.group(1).lower()

    exp_match = re.search(r"Explanation:\s*(.+)", content, re.IGNORECASE | re.DOTALL)
    if exp_match:
        explanation = exp_match.group(1).strip()

    return {"judgment": judgment, "explanation": explanation}
