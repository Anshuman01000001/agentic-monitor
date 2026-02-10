import argparse
from .chat import ChatSession

def main():
    parser = argparse.ArgumentParser(prog="slm-chat")
    parser.add_argument("prompt", nargs="?", help="Prompt to send. If omitted, interactive mode.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    args = parser.parse_args()

    chat = ChatSession()

    if args.prompt:
        chat.add_user(args.prompt)
        if args.no_stream:
            print(chat.complete())
        else:
            for tok in chat.stream():
                print(tok, end="", flush=True)
            print()
        return

    # Interactive loop
    while True:
        try:
            user = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not user:
            continue
        if user.lower() in {"exit", "quit"}:
            print("Bye.")
            break

        chat.add_user(user)
        for tok in chat.stream():
            print(tok, end="", flush=True)
        print()
