class GenerativeModel:
    def __init__(self, *args, **kwargs):
        pass
    def generate_content(self, *args, **kwargs):
        class R:
            text = ""
        return R()


def configure(api_key=""):
    pass


def list_models():
    class M:
        def __init__(self, name):
            self.name = name
    return [M("stub-model")]
