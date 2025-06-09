"""Ersatzmodul f\u00fcr OpenAI, das nur f\u00fcr Tests gedacht ist."""


class Client:
    """Platzhalter-Client zur Simulation der OpenAI-Bibliothek."""
    def __init__(self):
        pass

def ChatCompletion_create(*args, **kwargs):
    return {"choices": [{"message": {"content": ""}}]}

class ChatCompletion:
    """Minimaler Wrapper f\u00fcr ChatCompletion im Test."""
    create = staticmethod(ChatCompletion_create)
