class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderTransportError(ProviderError):
    pass


class ProviderAPIError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass
