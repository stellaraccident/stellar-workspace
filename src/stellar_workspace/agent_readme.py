"""Print the installed workspace operating guide."""
import argparse
from importlib.resources import files

TOPICS = ("init", "sandbox", "review", "config", "team", "machine")


def read(topic: str) -> str:
    return files("stellar_workspace").joinpath("resources", f"agent-{topic}.md").read_text()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", nargs="?", choices=TOPICS)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.all:
        print("\n\n".join(read(t) for t in ("overview", *TOPICS)))
    else:
        print(read(args.topic or "overview"))
    return 0
