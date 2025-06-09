"""Minimaler Torch-Stub f\u00fcr Testumgebungen."""


class cuda:
    """Nachbildung der CUDA-Schnittstelle."""
    @staticmethod
    def is_available():
        return False
