import pytest

from mywork_sdk.serve import server_options


def test_options_from_env():
    options = server_options({"MODULE": "hello.main", "ROOT_PATH": "/api/apps/hello"})
    assert options["app"] == "hello.main:app"
    assert options["root_path"] == "/api/apps/hello"
    assert options["port"] == 8000
    assert options["server_header"] is False


def test_custom_port():
    assert server_options({"MODULE": "core.main", "PORT": "9000"})["port"] == 9000


def test_module_required():
    with pytest.raises(SystemExit):
        server_options({})
