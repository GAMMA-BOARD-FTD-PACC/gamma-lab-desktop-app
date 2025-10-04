from .signal_dataset import SignalDataset
import numpy as np
import pyabf

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