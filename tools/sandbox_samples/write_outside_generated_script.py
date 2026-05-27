from pathlib import Path


def main():
    Path("../../outside_sandbox.txt").write_text("should be blocked", encoding="utf-8")


if __name__ == "__main__":
    main()
