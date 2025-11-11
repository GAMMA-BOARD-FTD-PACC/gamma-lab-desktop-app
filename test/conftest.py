import os, sys, pytest
import numpy as np

# Asegura que la RAÍZ del repo esté en sys.path (donde están core/, services/, etc.)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

@pytest.fixture
def dummy_path(tmp_path):
    # ruta ficticia para pasar a los loaders
    return str(tmp_path / "dummy.file")