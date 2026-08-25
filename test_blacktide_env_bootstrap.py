from pathlib import Path


def test_package_bootstraps_environment_before_shared_runtime_imports():
    source = (Path(__file__).parent / "bots" / "blacktide" / "__init__.py").read_text()
    assert source.index("bootstrap()") < source.index("from .runtime")
