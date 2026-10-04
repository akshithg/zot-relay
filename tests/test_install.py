import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client

from zot_relay import install as installer
from zot_relay import mcp


class AgentSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.executable = self.root / "connection program"
        self.executable.write_text("installed program")
        self.executable.chmod(0o700)

    def test_prepare_returns_a_client_independent_stdio_definition_and_plugin(self):
        with patch.object(installer, "mcp_executable", return_value=self.executable):
            result = installer.prepare_install()
        self.assertEqual(result["mcpServer"], {"command": str(self.executable), "args": []})
        self.assertEqual(result["serverName"], "zot-relay")
        self.assertEqual(Path(result["plugin"]), installer.bundled_bridge()[0])
        self.assertTrue(Path(result["plugin"]).is_file())
        self.assertEqual(result["pluginVersion"], installer.bundled_bridge()[1])
        self.assertTrue(result["ok"])

    def test_prepare_command_reports_json_and_leaves_client_settings_untouched(self):
        config = self.root / "config.toml"
        original = '# Existing settings\nmodel = "keep"\n'
        config.write_text(original)
        output = io.StringIO()
        with patch.dict(installer.os.environ, {"CODEX_HOME": str(self.root)}):
            with patch.object(installer, "mcp_executable", return_value=self.executable):
                with contextlib.redirect_stdout(output):
                    status = installer.main(["prepare"])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        self.assertEqual(config.read_text(), original)
        self.assertEqual(set(self.root.iterdir()), {config, self.executable})

    def test_missing_program_has_reinstallation_guidance(self):
        with patch.object(installer, "mcp_executable", return_value=self.root / "missing"):
            with self.assertRaisesRegex(RuntimeError, "Reinstall the Zot Relay package"):
                installer.prepare_install()

    def test_prepare_failure_has_nonzero_status_and_json_error(self):
        output = io.StringIO()
        with patch.object(installer, "prepare_install", side_effect=RuntimeError("missing program")):
            with contextlib.redirect_stdout(output):
                status = installer.main(["prepare"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue()), {"ok": False, "error": "missing program"})

    def test_windows_uses_console_launcher_suffix(self):
        with patch.object(installer.sys, "platform", "win32"):
            with patch.object(installer.sysconfig, "get_path", return_value=str(self.root)):
                self.assertEqual(installer.mcp_executable(), self.root / "zot-relay-mcp.exe")


class ConnectionCheckTests(unittest.IsolatedAsyncioTestCase):
    async def call_check(self, value, version=None, failure=None):
        server = mcp.create_server()
        response = {"ok": False, "error": failure} if failure else {"ok": True, "result": json.dumps(value)}
        responses = [io.BytesIO(json.dumps(response).encode())]
        if not failure:
            responses.append(io.BytesIO(json.dumps({"version": version}).encode()))
        # Replace only the subprocess transport; SDK discovery and calls remain real.
        with patch("mcp.Client", side_effect=lambda *args, **kwargs: Client(server)):
            with patch("urllib.request.urlopen", side_effect=responses) as send:
                result = await installer.check_connection()
        self.assertEqual(send.call_args_list[0].args[0].full_url, "http://127.0.0.1:24119/execute")
        sent = json.loads(send.call_args_list[0].args[0].data)
        self.assertEqual(sent, {"code": "return JSON.stringify({ok: true, zoteroVersion: Zotero.version});"})
        return result

    async def test_checks_sdk_tool_and_matching_bridge_without_writes(self):
        result = await self.call_check({"ok": True, "zoteroVersion": "10.0.5"}, installer.bundled_bridge()[1])
        self.assertEqual(result["bridgeVersion"], installer.bundled_bridge()[1])
        self.assertTrue(result["ok"])

    async def test_mismatched_bridge_is_not_reported_ready(self):
        with self.assertRaisesRegex(RuntimeError, "Install the plugin.*restart Zotero"):
            await self.call_check({"ok": True, "zoteroVersion": "10.0.5"}, "old-version")

    async def test_unexpected_result_is_not_reported_ready(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected connection-check result"):
            await self.call_check({"ok": True}, installer.bundled_bridge()[1])

    async def test_javascript_error_is_not_reported_ready(self):
        with self.assertRaisesRegex(RuntimeError, "JS evaluation error: check failed"):
            await self.call_check(None, failure="check failed")
