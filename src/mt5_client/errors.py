class MT5Error(RuntimeError):
    def __init__(self, message: str, retcode: int | None = None, last_error: object = None) -> None:
        super().__init__(message)
        self.retcode = retcode
        self.last_error = last_error
