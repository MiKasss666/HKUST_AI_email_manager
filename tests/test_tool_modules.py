"""Import every generated tool module with a tiny stub of the Dify SDK.

This catches syntax errors, wrong variable names and broken imports without
needing a Dify runtime or network access.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
TOOLS = os.path.join(PLUGIN, "tools")
sys.path.insert(0, PLUGIN)


def _install_stub():
    if "dify_plugin" in sys.modules:
        return
    dify_plugin = types.ModuleType("dify_plugin")

    class Tool:
        def __init__(self):
            self.session = types.SimpleNamespace(storage=None)

    class DifyPluginEnv:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Plugin:
        def __init__(self, env=None):
            self.env = env

        def run(self):
            pass

    class ToolProvider:
        def _validate_credentials(self, credentials):
            return None

    dify_plugin.Tool = Tool
    dify_plugin.ToolProvider = ToolProvider
    dify_plugin.DifyPluginEnv = DifyPluginEnv
    dify_plugin.Plugin = Plugin
    entities = types.ModuleType("dify_plugin.entities")
    tool_entities = types.ModuleType("dify_plugin.entities.tool")
    tool_entities.ToolInvokeMessage = object
    entities.tool = tool_entities
    dify_plugin.entities = entities
    sys.modules["dify_plugin"] = dify_plugin
    sys.modules["dify_plugin.entities"] = entities
    sys.modules["dify_plugin.entities.tool"] = tool_entities


class ToolModuleImportTests(unittest.TestCase):
    def test_import_all_tool_modules(self):
        _install_stub()
        files = sorted(name for name in os.listdir(TOOLS) if name.endswith(".py"))
        self.assertGreaterEqual(len(files), 15)
        for filename in files:
            path = os.path.join(TOOLS, filename)
            module_name = "email_manager_tool_" + filename[:-3]
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as ex:  # noqa: BLE001 - report which file failed
                self.fail(f"{filename} failed to import: {type(ex).__name__}: {ex}")

    def test_import_provider_and_main(self):
        _install_stub()
        for relative in ("provider/email_manager.py", "main.py"):
            path = os.path.join(PLUGIN, relative)
            module_name = "email_manager_" + relative.replace("/", "_")[:-3]
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as ex:  # noqa: BLE001
                self.fail(f"{relative} failed to import: {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
