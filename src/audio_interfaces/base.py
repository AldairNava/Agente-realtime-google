import abc

class AudioInterface(abc.ABC):
    @abc.abstractmethod
    async def read_chunk(self) -> bytes:
        """Lee un bloque de audio PCM."""
        pass

    @abc.abstractmethod
    async def write_chunk(self, data: bytes):
        """Escribe un bloque de audio PCM."""
        pass

    @abc.abstractmethod
    def close(self):
        """Cierra la interfaz de audio."""
        pass
