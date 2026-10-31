class TTSProviderError(Exception):
    pass


class TTSProviderConfigurationError(TTSProviderError):
    pass


class TTSProviderTransportError(TTSProviderError):
    pass


class TTSProviderAPIError(TTSProviderError):
    pass


class TTSProviderResponseError(TTSProviderError):
    pass
