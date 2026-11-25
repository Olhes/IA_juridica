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


class CohereChat:
    def __init__(self, api_key):
        self.client = cohere.AsyncClientV2(api_key=api_key)

    async def chat(self, *, message, preamble=None, chat_history=(), **options):
        result = await self.client.chat(messages=_messages(message, preamble, chat_history), **options)
        _record_usage(getattr(result, 'usage', None), options.get('model'))
        finish_reason = getattr(result, "finish_reason", None)
        _check_finish_reason(finish_reason, options.get("model"))
        return SimpleNamespace(
            text="".join(
                block.text for block in (result.message.content or []) if block.type == "text"
            ),
            finish_reason=finish_reason,
        )

    async def chat_stream(self, *, message, preamble=None, chat_history=(), **options):
        stream = self.client.chat_stream(messages=_messages(message, preamble, chat_history), **options)
        async for event in stream:
            if event.type == "content-delta":
                text = getattr(event.delta.message.content, "text", None)
                if text:
                    yield SimpleNamespace(text=text)
            elif event.type == 'message-end':
                delta = getattr(event, 'delta', None)
                _record_usage(getattr(delta, 'usage', None), options.get('model'))
                _check_finish_reason(getattr(delta, "finish_reason", None), options.get("model"))
