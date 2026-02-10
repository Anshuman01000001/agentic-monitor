from openai import OpenAI
from .config import Settings

def make_client(settings: Settings) -> OpenAI:
    #Just using the base_url for this OpenAI python client
    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)