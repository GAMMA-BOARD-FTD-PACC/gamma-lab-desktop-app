from pathlib import Path
from .signal_dataset import SignalDataset
import numpy as np
import pyabf
import pyedflib
from scipy.io import loadmat
import h5py

class FileIOService:
    """Lectura de archivos. Cada loader retorna un SignalDataset."""
    def load_abf(self, file_path: str) -> SignalDataset:
        print(f"\n=== Cargando archivo ABF: {file_path} ===")
        abf = pyabf.ABF(file_path)

        channel_count = abf.channelCount
        print(f"Channel count detectado: {channel_count}")

        time_data = abf.sweepX.copy()
        print(f"Time data obtenido, length: {len(time_data)}")
        print(f"Time range: {time_data[0]:.4f} - {time_data[-1]:.4f} segundos")

        signal_rows = []
        print("Leyendo canales:")
        for ch in range(channel_count):
            abf.setSweep(sweepNumber=0, channel=ch)
            y = abf.sweepY.copy()
            signal_rows.append(y)
            print(f"  Canal {ch}: {len(y)} puntos")

        signals = np.stack(signal_rows, axis=0)

        channel_names = [str(n) for n in abf.adcNames]
        units = list(abf.adcUnits)
        print(f"Channel names: {channel_names}")
        print(f"Units: {units}")

        sampling_rate = float(abf.dataRate)
        print(f"Sampling rate: {sampling_rate} Hz")
        print("ABF procesado correctamente")

        ds = SignalDataset(
            name=Path(file_path).name,
            format="abf",
            source_path=file_path,
            sampling_rate=sampling_rate,
            time=time_data,
            signals=signals,
            channel_names=channel_names,
            units=units,
            metadata={
                "sweepCount": abf.sweepCount,
                "channelCount": channel_count,
                "protocolPath": getattr(abf, 'protocolPath', None),
            },
        )
        return ds
    
    
    def load_edf(self, file_path: str) -> SignalDataset:

        print(f"\n=== Cargando archivo EDF: {file_path} ===")
        edf = pyedflib.EdfReader(file_path)

        try:
            C = edf.signals_in_file
            print(f"Channel count detectado: {C}")

            signals_raw = []
            channel_names = []
            units = []
            fs_list = []
            durations = []

            print("Leyendo canales:")
            for i in range(C):
                sig = edf.readSignal(i)
                fs_i = float(edf.samplefrequency(i))
                name_i = edf.getLabel(i).strip() or f"ch{i}"
                unit_i = edf.getPhysicalDimension(i).strip() or "uV"

                signals_raw.append(np.asarray(sig, dtype=np.float64))
                channel_names.append(str(name_i))
                units.append(str(unit_i))
                fs_list.append(fs_i)
                durations.append(len(sig) / fs_i)
                print(f"  Canal {i}: {len(sig)} puntos, fs={fs_i}Hz, name={name_i}, unit={unit_i}")

            same_fs = all(abs(f - fs_list[0]) < 1e-9 for f in fs_list)
            same_len = len({len(s) for s in signals_raw}) == 1

            if same_fs and same_len:
                sampling_rate = fs_list[0]
                N = len(signals_raw[0])
                time = np.arange(N, dtype=np.float64) / sampling_rate
                signals = np.stack(signals_raw, axis=0) 
                print("EDF con fs y longitud uniformes.")
            else:
                print("Advertencia: Canales con distintos fs/longitudes. Resampleando…")
                sampling_rate = float(min(fs_list))
                T_common = float(min(durations))
                N = int(np.floor(T_common * sampling_rate))
                time = np.arange(N, dtype=np.float64) / sampling_rate

                resampled = []
                for sig, fs_i in zip(signals_raw, fs_list):
                    t_i = np.arange(sig.shape[0], dtype=np.float64) / fs_i
                    y_i = np.interp(time, t_i, sig)
                    resampled.append(y_i.astype(np.float64))
                signals = np.stack(resampled, axis=0)

            print(f"Time data creado: {len(time)} puntos")
            print(f"Time range: {time[0]:.4f} - {time[-1]:.4f} s")
            print(f"Sampling rate (común): {sampling_rate} Hz")

            ds = SignalDataset(
                name=Path(file_path).name,
                format="edf",
                source_path=file_path,
                sampling_rate=sampling_rate,
                time=time,
                signals=signals,
                channel_names=channel_names,
                units=units,
                metadata={
                    "channelCount": C,
                    "fs_list": fs_list,
                    "uniform": same_fs and same_len,
                },
            )
            print("EDF procesado correctamente")
            return ds

        finally:
            edf.close()


    def load_mat(self, file_path: str) -> SignalDataset:
        """
        Carga un archivo MATLAB (.mat) y lo convierte en un SignalDataset.
        Soporta tanto formato clásico (scipy) como v7.3 (HDF5).
        """
        print(f"\n=== Cargando archivo MAT: {file_path} ===")

        try:
            # Intentar con formato clásico
            mat_data = loadmat(file_path)
            valid_keys = [k for k in mat_data.keys() if not k.startswith("__")]
            print("Archivo cargado con scipy.io.loadmat")
        except NotImplementedError:
            with h5py.File(file_path, "r") as f:
                print("Archivo .mat en formato HDF5 (v7.3). Cargando con h5py...")
                keys = list(f.keys())
                print(f"Variables encontradas (HDF5): {keys}")

                # Filtrar canales numéricos válidos
                channels = []
                channel_names = []

                for key in keys:
                    data = f[key]
                    if not isinstance(data, h5py.Dataset):
                        continue

                    arr = np.array(data)

                    # Verificar si el dataset es numérico
                    if np.issubdtype(arr.dtype, np.number):
                        channels.append(arr.flatten())
                        channel_names.append(key)
                        print(f"  Canal {key}: {len(arr.flatten())} muestras")
                    else:
                        print(f"  ⚠️ Variable {key} ignorada (no numérica, tipo {arr.dtype})")

                if not channels:
                    raise ValueError("No se encontraron canales numéricos en el archivo .mat")

                # Normalizar longitud (rellenar con NaN para igualar)
                max_len = max(len(ch) for ch in channels)
                padded = [np.pad(ch, (0, max_len - len(ch)), constant_values=np.nan) for ch in channels]
                signals = np.stack(padded, axis=0)

                # Generar eje de tiempo ficticio si no está presente
                time_data = np.arange(max_len, dtype=float)
                sampling_rate = 1.0  # desconocida

                ds = SignalDataset(
                    name=Path(file_path).name,
                    format="mat",
                    source_path=file_path,
                    sampling_rate=sampling_rate,
                    time=time_data,
                    signals=signals,
                    channel_names=channel_names,
                    units=["a.u."] * len(channel_names),
                    metadata={"variables": keys},
                )

                print("Archivo .mat procesado correctamente.")
                return ds