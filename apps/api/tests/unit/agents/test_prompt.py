import hashlib
import re
from importlib.resources import files

from fornada_api.agents.attendant.prompt import PROMPT_FILE, load_system_prompt


def test_text_comes_from_the_file() -> None:
    file_text = (files("fornada_api.agents.attendant") / PROMPT_FILE).read_text(encoding="utf-8")
    assert load_system_prompt().text == file_text.replace("\r\n", "\n")


def test_same_content_same_version() -> None:
    assert load_system_prompt().version == load_system_prompt().version


def test_one_changed_character_changes_the_version() -> None:
    assert load_system_prompt("Olá!").version != load_system_prompt("Olá?").version


def test_line_endings_do_not_change_the_version() -> None:
    assert load_system_prompt("a\r\nb\r\n").version == load_system_prompt("a\nb\n").version


def test_version_matches_sha256_of_the_file() -> None:
    prompt = load_system_prompt()
    digest = hashlib.sha256(prompt.text.encode("utf-8")).hexdigest()
    assert prompt.version == f"sha256:{digest[:12]}"


def test_version_format() -> None:
    assert re.fullmatch(r"sha256:[0-9a-f]{12}", load_system_prompt().version)
