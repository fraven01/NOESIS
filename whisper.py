class DummyModel:
    def transcribe(self, *args, **kwargs):
        return {"text": ""}

def load_model(name, device=None):
    return DummyModel()
