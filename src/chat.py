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

    