"""Adapt internal prompt arguments to Cohere Chat v2."""
from types import SimpleNamespace
import logging
import math
from numbers import Real

import cohere

logger = logging.getLogger('ia_juridica.cohere')


def _record_usage(usage, model):
    """Log only provider-reported counts; never prompts, keys, or responses."""
    billed = getattr(usage, 'billed_units', None)
    input_tokens = getattr(billed, 'input_tokens', None)
    output_tokens = getattr(billed, 'output_tokens', None)
    if all(isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
           for value in (input_tokens, output_tokens)):
        logger.info('cohere_billed_usage model=%s input_tokens=%s output_tokens=%s',
                    model or 'unknown', input_tokens, output_tokens)


def _messages(message, preamble=None, chat_history=()):
    if chat_history:
        raise ValueError("Pass conversational history in the application prompt")
    return ([{"role": "system", "content": preamble}] if preamble else []) + [
        {"role": "user", "content": message}
    ]


def _check_finish_reason(finish_reason, model):
    if finish_reason == "MAX_TOKENS":
        logger.warning(
            "cohere_truncated_max_tokens model=%s", model or "unknown"
        )


def default_thinking_option(model, *, enabled=None, token_budget=None):
    """Build Cohere v2 `thinking` payload for reasoning-capable models.

    `command-a-plus` leaks raw chain-of-thought into visible `text` blocks when
    sent `{"type": "disabled"}` on long RAG prompts. Using a minimal hidden
    containment budget (`token_budget=64`) keeps reasoning isolated in the
    discarded `thinking` channel while keeping visible output clean and fast.
    """
    model_lower = (model or "").lower()
    is_plus = "command-a-plus" in model_lower
    is_reasoning = "command-a-reasoning" in model_lower
    if not (is_plus or is_reasoning):
        return None
    if enabled is None or token_budget is None:
        from config.settings import settings

        if enabled is None:
            enabled = settings.COHERE_THINKING_ENABLED
        if token_budget is None:
            token_budget = settings.COHERE_THINKING_TOKEN_BUDGET
    if enabled:
        payload = {"type": "enabled"}
        if token_budget is not None:
            payload["token_budget"] = token_budget
        return payload
    if is_plus:
        return {"type": "enabled", "token_budget": 64}
    return {"type": "disabled"}


def _with_default_thinking(options):
    if "thinking" in options:
        return options
    thinking = default_thinking_option(options.get("model"))
    if thinking is None:
        return options
    return {**options, "thinking": thinking}


class CohereChat:
    def __init__(self, api_key):
        self.client = cohere.AsyncClientV2(api_key=api_key)

    async def chat(self, *, message, preamble=None, chat_history=(), **options):
        call_options = _with_default_thinking(options)
        result = await self.client.chat(messages=_messages(message, preamble, chat_history), **call_options)
        _record_usage(getattr(result, 'usage', None), call_options.get('model'))
        finish_reason = getattr(result, "finish_reason", None)
        _check_finish_reason(finish_reason, call_options.get("model"))
        return SimpleNamespace(
            text="".join(
                block.text for block in (result.message.content or []) if block.type == "text"
            ),
            finish_reason=finish_reason,
        )

    async def chat_stream(self, *, message, preamble=None, chat_history=(), **options):
        call_options = _with_default_thinking(options)
        stream = self.client.chat_stream(messages=_messages(message, preamble, chat_history), **call_options)
        async for event in stream:
            if event.type == "content-delta":
                text = getattr(event.delta.message.content, "text", None)
                if text:
                    yield SimpleNamespace(text=text)
            elif event.type == 'message-end':
                delta = getattr(event, 'delta', None)
                _record_usage(getattr(delta, 'usage', None), call_options.get('model'))
                _check_finish_reason(getattr(delta, "finish_reason", None), call_options.get("model"))
