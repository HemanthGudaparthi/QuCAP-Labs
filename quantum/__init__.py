from .electron  import ElectronBackend
from .photonic  import PhotonicBackend
from .neutrino  import NeutrinoBackend

BACKENDS = {
    "electron": ElectronBackend,
    "photonic": PhotonicBackend,
    "neutrino": NeutrinoBackend,
}

def get_backend(hardware_type: str):
    cls = BACKENDS.get(hardware_type)
    if cls is None:
        raise ValueError(f"Unknown hardware type: {hardware_type}")
    return cls()
