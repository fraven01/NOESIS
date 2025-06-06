class Client:
    def __init__(self):
        pass

def ChatCompletion_create(*args, **kwargs):
    return {"choices": [{"message": {"content": ""}}]}

class ChatCompletion:
    create = staticmethod(ChatCompletion_create)
