from modules.intent_parser import IntentParser


def main() -> None:
    parser = IntentParser()

    examples = [
        "pomoc",
        "help",
        "pokaz menu",
        "show menu",
        "klucze sa w kuchni",
        "gdzie sa klucze",
        "przypomnij mi za 10 sekund zebym wstal",
        "focus 1 minute",
        "przerwa 1 minuta",
        "statu",
    ]

    for text in examples:
        result = parser.parse(text)
        print(f"\nINPUT: {text}")
        print(f"ACTION: {result.action}")
        print(f"DATA: {result.data}")
        print(f"CONFIRM: {result.needs_confirmation}")
        print(f"SUGGESTIONS: {result.suggestions}")


if __name__ == "__main__":
    main()