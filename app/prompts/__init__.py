"""Jinja2 prompt template loader."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_SEPARATOR = "---"

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: object) -> str:
    """Render a prompt template with the given variables."""
    return _env.get_template(template_name).render(**kwargs)


def render_parts(template_name: str, **kwargs: object) -> tuple[str, str]:
    """Render a prompt template and split into (system, user) on '---' separator."""
    text = render(template_name, **kwargs)
    system, _, user = text.partition(_SEPARATOR)
    return system.strip(), user.strip()
