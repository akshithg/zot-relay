import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from mcp import Client

from zot_relay import mcp


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = mcp.create_server()

    async def test_discovery_exposes_one_tool_with_code_and_optional_timeout(self):
        async with Client(self.server) as client:
            tools = (await client.list_tools()).tools
        self.assertEqual([tool.name for tool in tools], ["eval_zotero"])
        tool = tools[0]
        self.assertEqual(tool.input_schema["required"], ["code"])
        self.assertEqual(tool.input_schema["properties"]["code"]["type"], "string")
        self.assertEqual(tool.input_schema["properties"]["timeout_seconds"]["default"], 60)
        self.assertFalse(tool.annotations.read_only_hint)
        self.assertTrue(tool.annotations.destructive_hint)
        self.assertFalse(tool.annotations.idempotent_hint)
        self.assertIn("bare async function body", tool.description)

    async def test_results_and_bridge_request(self):
        for value in [{"ok": True}, [1, "two"], 42, False, None, "plain text"]:
            with self.subTest(value=value):
                response = io.BytesIO(json.dumps({"ok": True, "result": json.dumps(value)}).encode())
                with patch("urllib.request.urlopen", return_value=response) as send:
                    async with Client(self.server) as client:
                        result = await client.call_tool(
                            "eval_zotero", {"code": "return JSON.stringify(value);", "timeout_seconds": 5}
                        )
                self.assertFalse(result.is_error)
                # Objects stay intact; other JSON values use a "result" field.
                expected = value if isinstance(value, dict) else {"result": value}
                self.assertEqual(result.structured_content, expected)
                request = send.call_args.args[0]
                self.assertEqual(request.full_url, "http://127.0.0.1:24119/execute")
                self.assertEqual(json.loads(request.data), {"code": "return JSON.stringify(value);"})
                self.assertEqual(request.get_header("X-zev-client"), "1")
                self.assertEqual(send.call_args.kwargs["timeout"], 5)

    async def test_non_json_text_is_preserved(self):
        response = io.BytesIO(b'{"ok":true,"result":"plain text"}')
        with patch("urllib.request.urlopen", return_value=response):
            async with Client(self.server) as client:
                result = await client.call_tool("eval_zotero", {"code": "return 'plain text';"})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {"result": "plain text"})

    async def test_invalid_arguments_do_not_reach_zotero(self):
        arguments = [
            {"code": " \n"},
            {"code": 42},
            {},
            {"code": "return 1;", "timeout_seconds": 0},
            {"code": "return 1;", "timeout_seconds": -1},
            {"code": "return 1;", "timeout_seconds": "invalid"},
        ]
        with patch("urllib.request.urlopen") as send:
            async with Client(self.server) as client:
                for args in arguments:
                    with self.subTest(args=args):
                        result = await client.call_tool("eval_zotero", args)
                        self.assertTrue(result.is_error)
        send.assert_not_called()

    async def test_nonfinite_timeouts_are_rejected(self):
        # JSON cannot represent these values; the direct SDK path also rejects them.
        with patch("urllib.request.urlopen") as send:
            async with Client(self.server) as client:
                for timeout in [float("nan"), float("inf"), float("-inf")]:
                    with self.subTest(timeout=timeout):
                        result = await client.call_tool(
                            "eval_zotero", {"code": "return 1;", "timeout_seconds": timeout}
                        )
                        self.assertTrue(result.is_error)
        send.assert_not_called()

    async def test_errors_reach_client_without_retry(self):
        failures = [
            (TimeoutError(), "Verify the affected state before retrying"),
            (urllib.error.URLError("Connection refused"), "Is Zotero running"),
        ]
        for error, message in failures:
            with self.subTest(error=error):
                with patch("urllib.request.urlopen", side_effect=error) as send:
                    async with Client(self.server) as client:
                        result = await client.call_tool("eval_zotero", {"code": "return 1;"})
                self.assertTrue(result.is_error)
                self.assertIn(message, result.content[0].text)
                self.assertEqual(send.call_count, 1)

    async def test_javascript_failure_is_a_tool_error(self):
        response = io.BytesIO(b'{"ok":false,"error":"deliberate failure"}')
        with patch("urllib.request.urlopen", return_value=response) as send:
            async with Client(self.server) as client:
                result = await client.call_tool("eval_zotero", {"code": "throw Error('deliberate failure');"})
        self.assertTrue(result.is_error)
        self.assertIn("JS evaluation error: deliberate failure", result.content[0].text)
        self.assertEqual(send.call_count, 1)
