class VideoProviderError(Exception):
    pass


class VideoProviderConfigurationError(VideoProviderError):
    pass


class VideoProviderTransportError(VideoProviderError):
    pass


class VideoProviderAPIError(VideoProviderError):
    pass


class VideoProviderResponseError(VideoProviderError):
    pass


class VideoProviderTimeoutError(VideoProviderError):
    pass
