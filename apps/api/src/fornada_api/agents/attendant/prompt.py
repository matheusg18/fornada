"""The attendant's system prompt and its version.

The prompt is a Markdown file. Its version is a hash of the content, so any
edit gives a new version and the same text always gives the same one. See the
`prompt-versioning` spec.
"""

import hashlib
from dataclasses import dataclass
from importlib.resources import files

PROMPT_FILE = "prompts/system.md"
VERSION_PREFIX = "sha256:"
VERSION_DIGITS = 12


@dataclass(frozen=True)
class SystemPrompt:
    text: str
    version: str


def prompt_version(text: str) -> str:
    return VERSION_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()[:VERSION_DIGITS]


def load_system_prompt(source: str | None = None) -> SystemPrompt:
    """Load the prompt from the package file, or from `source` text (tests)."""
    if source is None:
        source = (files(__package__) / PROMPT_FILE).read_text(encoding="utf-8")
    # The hash covers exactly what the model sees, whatever the file's line endings.
    text = source.replace("\r\n", "\n")
    return SystemPrompt(text=text, version=prompt_version(text))
