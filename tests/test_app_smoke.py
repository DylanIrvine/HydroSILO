"""Boot the Streamlit front end headless and check the page builds."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_boots():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "HydroSILO"
    labels = [e.label for e in at.expander]
    assert any("Privacy" in label for label in labels)
    assert any("cite" in label for label in labels)
    assert any(c.value.startswith("Version ") for c in at.caption)
