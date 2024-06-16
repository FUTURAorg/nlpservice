import threading
from .CTCBackend import CTCBackend

class SingletonMeta(type):
    """
    This is a thread-safe implementation of Singleton.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with threading.Lock():
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class BackendHolder(metaclass=SingletonMeta):
    def __init__(self, initialBackend = 'CTCBackend'):
        self.__backends = {
            "CTCBackend": CTCBackend,
            "WhisperBackend": WhisperBackend
        }
        self.current_backend = self.__backends[initialBackend]()
    
    def change_backend(self, backend_name):
        if backend_name in self.__backends:
            self.current_backend = self.__backends[backend_name]()
            return True, "Backend changed successfully."
        else:
            return False, "Backend not found."
    
    def get_backend(self):
        return self.current_backend
    
    def list_backends(self):
        return list(self.__backends.keys())