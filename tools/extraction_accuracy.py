"""Measure extraction accuracy on a corpus with ground truth (PLT-02, TC-ING-02-1, TC-ING-03-1).

    uv run python tools/extraction_accuracy.py tests/corpus-holdout            # the layout rules
    uv run python tools/extraction_accuracy.py tests/corpus-holdout --extractor claude

`--extractor claude` needs MHS_ANTHROPIC_API_KEY (and network access); it sends each document's scrubbed text with
its dates shifted, exactly as the AI worker does (PRV-01, PRV-05). Synthetic corpora only.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mhs.ingest.accuracy import TARGET, evaluate  # noqa: E402
from mhs.ingest.extract import extract  # noqa: E402


def claude_extractor():
    from mhs.ingest.ai import DATES, ClaudeExtractor, config_from_env
    from mhs.ingest.dates import new_offset, shift_iso, shift_text

    ai = ClaudeExtractor(config_from_env())

    def run(text: str):
        days = new_offset()
        x = ai.extract(shift_text(text, days))
        for name in DATES:
            if name in x.fields and isinstance(x.fields[name].value, str):
                x.fields[name].value = shift_iso(x.fields[name].value, -days)
        return x

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--extractor", choices=["rules", "claude"], default="rules")
    args = parser.parse_args()
    report = evaluate(args.corpus, claude_extractor() if args.extractor == "claude" else extract)
    print(f"Extractor: {args.extractor}\n")
    print(report.markdown())
    sys.exit(0 if report.classification >= TARGET and report.amounts >= TARGET else 1)


if __name__ == "__main__":
    main()
