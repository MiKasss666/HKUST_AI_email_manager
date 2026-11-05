"""Tool provider for the Email Manager plugin.

The plugin does not use Dify-managed OAuth credentials: device-code sign-in is
performed by the ``auth_*`` tools and the resulting tokens live in the plugin's
persistent storage (workspace scoped). There is therefore nothing to validate
here.
"""

from dify_plugin import ToolProvider


class EmailManagerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        return None
