import base64
import datetime as dt
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hours


class HoursTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'HOURS_DIR': self.temp.name})
        self.env.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.env.stop)

    def write(self, day, text):
        path = hours.day_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_dates_and_boundaries(self):
        today = dt.date(2026, 11, 18)
        self.assertEqual(hours.resolve_date('-tue', today), dt.date(2026, 11, 17))
        self.assertEqual(hours.resolve_date('-wed', today), today)
        self.assertEqual(hours.resolve_date('-fri', today), dt.date(2026, 11, 13))
        self.assertEqual(hours.resolve_date('-1', today, True), dt.date(2026, 11, 9))
        self.assertEqual(hours.resolve_date('-1', dt.date(2026, 1, 1)), dt.date(2025, 12, 31))
        self.assertEqual(hours.resolve_date('+1', today), dt.date(2026, 11, 19))
        with self.assertRaises(ValueError):
            hours.resolve_date('-tue', today, True)

    def test_markdown_and_export(self):
        day = dt.date(2026, 11, 18)
        self.write(day, '# Wednesday\n\n- 1h Meeting with John\n- 15m Sending e-mails\n- 1h30m Build\n')
        self.assertEqual(sum(e[0] for e in hours.read_entries(day)), Decimal(165))
        self.assertEqual(hours.export_tsv([day]), 'Date\tHours\tActivity\n2026-11-18\t1\tMeeting with John\n2026-11-18\t0.25\tSending e-mails\n2026-11-18\t1.5\tBuild\n')
        self.assertTrue(str(hours.day_path(day)).endswith('/2026/11/18.md'))

    def test_invalid_entries_are_not_silently_dropped(self):
        day = dt.date(2026, 11, 18)
        for line in ('- 2x Work', '- h Work', 'forgot bullet', '- 1h'):
            self.write(day, line)
            with self.assertRaises(ValueError):
                hours.read_entries(day)

    def test_spreadsheet_cells(self):
        day = dt.date(2026, 11, 18)
        self.write(day, '- 30m =SUM(A1:A2)\n- 0.5h a\tb\n')
        self.assertIn("\t'=SUM(A1:A2)\n", hours.export_tsv([day]))
        self.assertIn('\ta b\n', hours.export_tsv([day]))

    def test_editor_reopens_same_file_without_overwriting(self):
        day = dt.date(2026, 11, 18)
        self.write(day, '- 1h Existing\n')
        with patch.dict(os.environ, {'HOURS_EDITOR': 'nvim -u NONE'}), patch('hours.subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertEqual(hours.edit_day(day), '2026-11-18: 1h')
            run.assert_called_once_with(['nvim', '-u', 'NONE', str(hours.day_path(day))])
        self.assertEqual(hours.day_path(day).read_text(), '- 1h Existing\n')

    def test_neovim_clean_default_and_explicit_override(self):
        with patch.dict(os.environ, {'EDITOR': 'nvim'}, clear=True):
            self.assertEqual(hours.editor_command(), ['nvim', '--clean'])
        with patch.dict(os.environ, {'HOURS_EDITOR': 'nvim'}, clear=True):
            self.assertEqual(hours.editor_command(), ['nvim'])

    def test_terminal_clipboard_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch('hours.sys.stdout') as out:
            out.isatty.return_value = True
            self.assertEqual(hours.copy_clipboard('Date\tHours\n'), 'terminal clipboard request')
            encoded = base64.b64encode(b'Date\tHours\n').decode('ascii')
            out.write.assert_called_once_with(f'\033]52;c;{encoded}\a')

    def test_clipboard_backend_does_not_pipe_daemon_stderr(self):
        with patch.dict(os.environ, {'DISPLAY': ':0'}, clear=True), patch('hours.shutil.which', return_value='/usr/bin/xclip'), patch('hours.subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertEqual(hours.copy_clipboard('hello'), 'system clipboard')
            self.assertNotEqual(run.call_args.kwargs['stderr'], hours.subprocess.PIPE)
            self.assertEqual(run.call_args.kwargs['input'], b'hello')

    def test_clipboard_failure_when_redirected(self):
        with patch.dict(os.environ, {}, clear=True), patch('hours.sys.stdout') as out:
            out.isatty.return_value = False
            with self.assertRaises(ValueError):
                hours.copy_clipboard('hello')

    def test_empty_week(self):
        self.assertEqual(hours.export_tsv(hours.week_days(dt.date(2026, 11, 16))), 'Date\tHours\tActivity\n')


if __name__ == '__main__':
    unittest.main()
