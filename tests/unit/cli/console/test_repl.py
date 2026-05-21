import io
import signal
import sys
import unittest
from unittest.mock import patch

from cli.console import repl


class TestNormalize(unittest.TestCase):
    def test_empty_argv_becomes_help(self):
        self.assertEqual(repl._normalize([]), ["--help"])

    def test_strips_infinito_prefix(self):
        self.assertEqual(repl._normalize(["infinito", "meta", "env"]), ["meta", "env"])

    def test_strips_cli_prefix(self):
        self.assertEqual(repl._normalize(["cli", "build", "tree"]), ["build", "tree"])

    def test_bare_infinito_becomes_help(self):
        self.assertEqual(repl._normalize(["infinito"]), ["--help"])

    def test_help_alias_lowercase(self):
        self.assertEqual(repl._normalize(["help"]), ["--help"])

    def test_help_alias_question_mark(self):
        self.assertEqual(repl._normalize(["?"]), ["--help"])

    def test_help_alias_h(self):
        self.assertEqual(repl._normalize(["h"]), ["--help"])

    def test_help_alias_preserves_following_args(self):
        self.assertEqual(repl._normalize(["help", "meta"]), ["--help", "meta"])

    def test_pass_through_unknown(self):
        self.assertEqual(repl._normalize(["meta", "env"]), ["meta", "env"])

    def test_strip_then_help_alias(self):
        self.assertEqual(repl._normalize(["infinito", "help"]), ["--help"])


class TestRunCli(unittest.TestCase):
    @patch("cli.console.repl.subprocess.run")
    def test_invokes_python_m_cli_with_argv(self, mock_run):
        mock_run.return_value.returncode = 0
        rc = repl._run_cli(["meta", "env"])
        self.assertEqual(rc, 0)
        called_argv = mock_run.call_args[0][0]
        self.assertEqual(called_argv[0], sys.executable)
        self.assertEqual(called_argv[1:], ["-m", "cli", "meta", "env"])

    @patch("cli.console.repl.subprocess.run")
    def test_restores_sigint_handler(self, mock_run):
        mock_run.return_value.returncode = 0
        before = signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            repl._run_cli(["x"])
            after = signal.getsignal(signal.SIGINT)
            self.assertEqual(after, signal.SIG_DFL)
        finally:
            signal.signal(signal.SIGINT, before)


class TestMainLoop(unittest.TestCase):
    def _run_with_inputs(self, inputs):
        captured_calls = []

        def fake_input(prompt):
            if not inputs:
                raise EOFError
            value = inputs.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        def fake_run_cli(argv):
            captured_calls.append(argv)
            return 0

        with (
            patch("builtins.input", side_effect=fake_input),
            patch("cli.console.repl._run_cli", side_effect=fake_run_cli),
            patch("sys.stdout", new_callable=io.StringIO) as out,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            rc = repl.main()
        return rc, captured_calls, out.getvalue()

    def test_eof_exits_cleanly(self):
        rc, calls, _ = self._run_with_inputs([])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_exit_token(self):
        rc, calls, _ = self._run_with_inputs(["exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_quit_token(self):
        rc, _calls, _ = self._run_with_inputs(["quit"])
        self.assertEqual(rc, 0)

    def test_vim_style_quit(self):
        rc, _calls, _ = self._run_with_inputs([":q"])
        self.assertEqual(rc, 0)

    def test_blank_input_is_skipped(self):
        rc, calls, _ = self._run_with_inputs(["", "   ", "exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_keyboard_interrupt_does_not_exit(self):
        rc, calls, _ = self._run_with_inputs([KeyboardInterrupt(), "exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_command_is_normalized_and_dispatched(self):
        rc, calls, _ = self._run_with_inputs(["infinito meta env", "exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["meta", "env"]])

    def test_help_alias_is_dispatched_as_help_flag(self):
        rc, calls, _ = self._run_with_inputs(["help", "exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["--help"]])

    def test_shlex_parse_error_is_caught(self):
        rc, calls, _ = self._run_with_inputs(["echo 'unterminated", "exit"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_banner_is_printed_once(self):
        _, _, out = self._run_with_inputs(["exit"])
        self.assertEqual(out.count("infinito.nexus console"), 1)
        self.assertIn(repl.WEB_URL, out)
        self.assertIn(repl.DOCS_URL, out)
        self.assertIn(repl.LICENSE_NAME, out)
        self.assertIn(repl.LICENSE_URL, out)
        self.assertIn(repl.AUTHOR, out)


if __name__ == "__main__":
    unittest.main()
