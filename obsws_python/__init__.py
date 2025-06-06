class ReqClient:
    def __init__(self, *args, **kwargs):
        pass
    def start_record(self):
        pass
    def stop_record(self):
        pass
    def get_record_status(self):
        class Status:
            output_active = False
        return Status()
