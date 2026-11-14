"""Adapt internal prompt arguments to Cohere Chat v2."""
from types import SimpleNamespace

import cohere


def _messages(message, preamble=None, chat_history=()):
    if chat_history:
        raise ValueError("Pass conversational history in the application prompt")
    return ([{"role": "system", "content": preamble}] if preamble else []) + [
        {"role": "user", "content": message}
    ]


class CohereChat:
    def __init__(self, api_key):
        self.client = cohere.AsyncClientV2(api_key=api_key)

    async def chat(self, *, message, preamble=None, chat_history=(), **options):
        result = await self.client.chat(messages=_messages(message, preamble, chat_history), **options)
        return SimpleNamespace(text="".join(
            block.text for block in (result.message.content or []) if block.type == "text"
        ))

    async def chat_stream(self, *, message, preamble=None, chat_history=(), **options):
        stream = self.client.chat_stream(messages=_messages(message, preamble, chat_history), **options)
        async for event in stream:
            if event.type == "content-delta":
                text = getattr(event.delta.message.content, "text", None)
                if text:
                    yield SimpleNamespace(text=text)
