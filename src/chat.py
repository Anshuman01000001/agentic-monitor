from typing import List, Dict, Iterator, Optional
from .config import Settings
from .client import make_client

Message = Dict[str, str]

class ChatSession:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.client = make_client(self.settings)
        self.messages: List[Message] = [{"role": "system", "content": "You are a helpful assistant."}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def complete(self) -> str:
        resp = self.client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            messages=self.messages,
            timeout=self.settings.timeout_s,
        )
        text = resp.choices[0].message.content or ""
        self.add_assistant(text)
        return text

    def stream(self) -> Iterator[str]:
        resp = self.client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            messages=self.messages,
            stream=True,
            timeout=self.settings.timeout_s,
        )
        chunks = []
        for event in resp:
            delta = event.choices[0].delta
            token = getattr(delta, "content", None)
            if token:
                chunks.append(token)
                yield token
        full = "".join(chunks)
        self.add_assistant(full)