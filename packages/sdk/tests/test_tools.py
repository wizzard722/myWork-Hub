import pytest
from pydantic import ValidationError

from mywork_sdk import AppManifest, ToolSpec


def test_tool_confirmation_defaults():
    read = ToolSpec(name="list_items", description="Toon alle items", path="/items")
    write = ToolSpec(name="add_item", description="Voeg een item toe", method="POST", path="/items")
    assert not read.needs_confirmation
    assert write.needs_confirmation
    forced = ToolSpec(name="peek", description="Gevoelige lees-actie", path="/x", confirm=True)
    assert forced.needs_confirmation


@pytest.mark.parametrize("name", ["Hoofdletter", "1begin", "met-streep", "x"])
def test_tool_name_rules(name):
    with pytest.raises(ValidationError):
        ToolSpec(name=name, description="Omschrijving lang genoeg", path="/x")


def test_manifest_with_tools():
    manifest = AppManifest(
        id="demo",
        name="Demo",
        version="1",
        tools=[{"name": "greet", "description": "Begroet iemand", "path": "/greetings/{name}"}],
    )
    assert manifest.tools[0].method == "GET"
