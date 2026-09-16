"""Check the packages used by the IR/NLP agent without blocking the baseline."""

from importlib.util import find_spec

import pypdf


def is_installed(module_name: str) -> bool:
    try:
        return bool(find_spec(module_name))
    except ModuleNotFoundError:
        return False

print("Core environment is working!")
print("pypdf:", pypdf.__version__)
print("spaCy NLP upgrade installed:", is_installed("spacy"))
print("Gemini semantic-search upgrade installed:", is_installed("google.genai"))
