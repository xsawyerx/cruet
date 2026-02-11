"""Phase 0: Verify the C extension compiles, imports, and exposes basic API."""


def test_import_cruet():
    """cruet package is importable."""
    import cruet
    assert cruet is not None


def test_import_c_extension():
    """The C extension module is importable."""
    from cruet import _cruet
    assert _cruet is not None


def test_version_string():
    """__version__ is a non-empty string."""
    import cruet
    assert isinstance(cruet.__version__, str)
    assert len(cruet.__version__) > 0


def test_version_value():
    """__version__ returns the expected value."""
    import cruet
    assert cruet.__version__ == "0.1.0"


def test_version_function():
    """The C version() function works."""
    from cruet._cruet import version
    assert version() == "0.1.0"


def test_module_name():
    """Module __name__ is correct."""
    from cruet import _cruet
    assert _cruet.__name__ == "cruet._cruet"
