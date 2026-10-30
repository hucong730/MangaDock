class ImageProviderError(Exception):
    pass


class ImageProviderConfigurationError(ImageProviderError):
    pass


class ImageProviderTransportError(ImageProviderError):
    pass


class ImageProviderAPIError(ImageProviderError):
    pass


class ImageProviderResponseError(ImageProviderError):
    pass


class ImageProviderTimeoutError(ImageProviderError):
    pass
