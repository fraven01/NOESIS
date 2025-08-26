class GenerativeModel:
    def __init__(self, *args, **kwargs):
        pass
    def generate_content(self, *args, **kwargs):
        class Part:
            text = "Stubantwort"
        class Content:
            parts = [Part()]
        class Candidate:
            finish_reason = "stop"
            content = Content()
        class R:
            text = Part.text
            candidates = [Candidate()]
            usage_metadata = type(
                "U",
                (),
                {
                    "prompt_token_count": 0,
                    "candidates_token_count": 0,
                    "total_token_count": 0,
                },
            )()
        return R()


def configure(api_key=""):
    pass


def list_models():
    class M:
        def __init__(self, name):
            self.name = name
    return [M("stub-model")]
