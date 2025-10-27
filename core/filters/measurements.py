import numpy as np

def two_point_metrics(p1, p2, kind="slope"):
    """
    p1, p2: tuplas (x, y)
    kind: tipo de medición ('slope', más adelante podrías agregar 'delta', etc.)
    """
    x1, y1 = map(np.float64, p1)
    x2, y2 = map(np.float64, p2)

    dx = x2 - x1
    dy = y2 - y1

    # pendiente y distancia euclídea
    slope = np.inf if dx == 0 else dy / dx
    dist = np.hypot(dx, dy)

    # salida homogénea
    return {
        "type": kind,
        "p1": (float(x1), float(y1)),
        "p2": (float(x2), float(y2)),
        "dx": float(dx),
        "dy": float(dy),
        "slope": float(slope),
        "dist": float(dist),
    }