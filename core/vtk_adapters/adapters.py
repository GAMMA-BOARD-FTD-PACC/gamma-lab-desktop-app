import vtk
import numpy as np
from vtkmodules.util import numpy_support
from core.services.fileio import SignalDataset

def dataset_to_vtk_table(ds: SignalDataset) -> vtk.vtkTable:
    """
    Convierte el dataset a una vtkTable:
    - Columna 0: time
    - Columnas 1..C: cada canal
    Cachea en ds.vtk_table para no repetir trabajo.
    """
    if ds.vtk_table is not None:
        return ds.vtk_table

    C, N = ds.signals.shape
    assert ds.time.shape[0] == N, "time y signals no coinciden en longitud"

    table = vtk.vtkTable()

    # columna time
    arr_time = numpy_support.numpy_to_vtk(ds.time.astype(np.float64), deep=True)
    arr_time.SetName("time")
    table.AddColumn(arr_time)

    # columnas por canal
    for ch in range(C):
        arr = numpy_support.numpy_to_vtk(ds.signals[ch].astype(np.float64), deep=True)
        name = ds.channel_names[ch] if ch < len(ds.channel_names) else f"ch{ch}"
        arr.SetName(name)
        table.AddColumn(arr)

    table.SetNumberOfRows(N)
    ds.vtk_table = table
    return table