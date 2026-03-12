class BaseChannel:
    """
    Interfaz base para canales de mensajería.
    """

    def get_updates(self, offset=None):
        raise NotImplementedError

    def send_message(self, chat_id: int, text: str):
        raise NotImplementedError