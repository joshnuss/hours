#!/usr/bin/env python3
"""Markdown hours journal, with a Vim-friendly weekly terminal view."""
import base64
import curses
import datetime as dt
from decimal import Decimal
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
ENTRY = re.compile(r'^\s*-\s+(\S+)\s+(.+?)\s*$')
DURATION = re.compile(r'(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?$')


def data_dir():
    return Path(os.environ.get('HOURS_DIR', '~/hours')).expanduser().resolve()


def day_path(day):
    return data_dir() / f'{day.year:04}' / f'{day.month:02}' / f'{day.day:02}.md'


def resolve_date(selector=None, today=None, weekly=False):
    today = today or dt.date.today()
    if weekly:
        today -= dt.timedelta(days=today.weekday())
    if selector is None:
        return today
    if re.fullmatch(r'[+-]?\d+', selector):
        return today + dt.timedelta(days=int(selector) * (7 if weekly else 1))
    if not weekly and selector.startswith('-') and selector[1:].lower() in DAYS:
        return today - dt.timedelta(days=(today.weekday() - DAYS.index(selector[1:].lower())) % 7)
    raise ValueError('Use a day offset such as -1, +2, or -tue; week offsets must be numbers.')


def read_entries(day):
    path = day_path(day)
    if not path.exists():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = ENTRY.fullmatch(line)
        duration = DURATION.fullmatch(match[1]) if match else None
        if not duration or not any(duration.groups()):
            raise ValueError(f'{path}:{number}: expected "- 1h Activity" or "- 15m Activity" (also supports 1h30m).')
        minutes = Decimal(duration[1] or '0') * 60 + Decimal(duration[2] or '0')
        entries.append((minutes, match[2]))
    return entries


def duration_label(minutes):
    hours, remaining = divmod(minutes, 60)
    return ' '.join(part for part in (f'{hours:g}h' if hours else '', f'{remaining:g}m' if remaining else '') if part) or '0m'


def editor_command():
    explicit = os.environ.get('HOURS_EDITOR')
    if explicit:
        command = shlex.split(explicit)
        if not command:
            raise ValueError('HOURS_EDITOR must contain an editor command.')
        return command
    setting = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if setting:
        command = shlex.split(setting)
        if command:
            if Path(command[0]).name == 'nvim' and len(command) == 1:
                command.append('--clean')
            return command
    for name in ('nvim', 'vim', 'vi', 'nano'):
        if shutil.which(name):
            return [name, '--clean'] if name == 'nvim' else [name]
    raise ValueError('No editor found. Install Neovim or set HOURS_EDITOR.')


def edit_day(day):
    command = editor_command()
    path = day_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Leave new files to the editor: quitting without saving creates no entry.
    result = subprocess.run(command + [str(path)])
    if result.returncode:
        raise ValueError(f'Editor exited with status {result.returncode}.')
    entries = read_entries(day)
    return f'{day.isoformat()}: {duration_label(sum((e[0] for e in entries), Decimal(0)))}'


def week_days(start):
    return [start + dt.timedelta(days=i) for i in range(7)]


def export_tsv(days):
    rows = ['Date\tHours\tActivity']
    for day in days:
        for minutes, activity in read_entries(day):
            hours = format(minutes / 60, '.6f').rstrip('0').rstrip('.')
            # Keep each activity in one cell and prevent spreadsheet formula execution.
            activity = activity.replace('\t', ' ')
            if activity.lstrip().startswith(('=', '+', '-', '@')):
                activity = "'" + activity
            rows.append(f'{day.isoformat()}\t{hours}\t{activity}')
    return '\n'.join(rows) + '\n'


def copy_clipboard(text):
    candidates = []
    if sys.platform == 'darwin':
        candidates.append(['pbcopy'])
    if os.environ.get('WAYLAND_DISPLAY'):
        candidates.append(['wl-copy'])
    if os.environ.get('DISPLAY'):
        candidates.extend([['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']])
    if sys.platform == 'win32':
        candidates.append(['clip.exe'])
    for command in candidates:
        if shutil.which(command[0]):
            # xclip forks a clipboard owner that retains stderr. A PIPE here
            # makes communicate() wait until another app replaces the clipboard.
            with tempfile.TemporaryFile() as errors:
                try:
                    result = subprocess.run(command, input=text.encode('utf-8'),
                                            stderr=errors, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    continue
            if result.returncode == 0:
                return 'system clipboard'
    if sys.stdout.isatty():
        # OSC 52 asks the user's terminal (including Ghostty) to copy the text.
        # This also works when the process cannot reach a graphical display.
        encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
        sequence = f'\033]52;c;{encoded}\a'
        if os.environ.get('TMUX'):
            sequence = '\033Ptmux;' + sequence.replace('\033', '\033\033') + '\033\\'
        sys.stdout.write(sequence)
        sys.stdout.flush()
        return 'terminal clipboard request'
    raise ValueError('Cannot access the clipboard. Run in a terminal with OSC 52 support, install wl-clipboard/xclip, or use --stdout.')


def print_week(start):
    total = Decimal(0)
    for day in week_days(start):
        entries = read_entries(day)
        minutes = sum((e[0] for e in entries), Decimal(0))
        total += minutes
        print(f'{day:%a %Y-%m-%d}  {duration_label(minutes)}')
        for amount, activity in entries:
            print(f'  {duration_label(amount):>8}  {activity}')
    print(f'Week total: {duration_label(total)}')


def weekly_ui(start):
    def run(screen):
        nonlocal start
        selected = dt.date.today().weekday()
        message = ''
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        def put(y, text, style=0):
            height, width = screen.getmaxyx()
            if 0 <= y < height and width > 1:
                try:
                    screen.addnstr(y, 0, text, width - 1, style)
                except curses.error:
                    pass
        while True:
            screen.erase()
            days = week_days(start)
            put(0, f'HOURS  {start:%b %d, %Y} – {days[-1]:%b %d, %Y}', curses.A_BOLD)
            total = Decimal(0)
            current = []
            for i, day in enumerate(days):
                try:
                    entries = read_entries(day)
                    minutes = sum((e[0] for e in entries), Decimal(0))
                    total += minutes
                    label = f'{duration_label(minutes):>9}  {len(entries)} entries'
                except ValueError:
                    entries = []
                    label = 'INVALID ENTRY — press Enter to fix'
                if i == selected:
                    current = entries
                put(i + 2, f'{">" if i == selected else " "} {day:%a %m/%d}  {label}', curses.A_REVERSE if i == selected else 0)
            put(10, f'Week total: {duration_label(total)}', curses.A_BOLD)
            height, _ = screen.getmaxyx()
            for i, (amount, activity) in enumerate(current[:max(0, height - 16)]):
                put(12 + i, f'  {duration_label(amount):>8}  {activity}')
            put(height - 3, message)
            put(height - 2, 'j/k: day  h/l: week  Enter: edit  t: today  y: copy week  q: quit')
            screen.refresh()
            key = screen.getch()
            message = ''
            if key in (ord('q'), 27):
                return
            if key in (ord('j'), curses.KEY_DOWN):
                selected = (selected + 1) % 7
            elif key in (ord('k'), curses.KEY_UP):
                selected = (selected - 1) % 7
            elif key in (ord('h'), curses.KEY_LEFT):
                start -= dt.timedelta(days=7)
            elif key in (ord('l'), curses.KEY_RIGHT):
                start += dt.timedelta(days=7)
            elif key == ord('t'):
                start = resolve_date(weekly=True)
                selected = dt.date.today().weekday()
            elif key == ord('y'):
                try:
                    target = copy_clipboard(export_tsv(days))
                    message = f'Week sent to {target}.'
                except ValueError as exc:
                    message = str(exc)
            elif key in (10, 13, curses.KEY_ENTER):
                curses.def_prog_mode()
                curses.endwin()
                try:
                    message = edit_day(days[selected])
                except (ValueError, OSError) as exc:
                    message = str(exc)
                finally:
                    curses.reset_prog_mode()
                    screen.clear()
    curses.wrapper(run)


HELP = '''Track hours in Markdown using Neovim (or your preferred editor).

Usage:
  hours                     Edit today
  hours -1                  Edit yesterday (also accepts +1, -2, ...)
  hours -tue                Edit the most recent Tuesday, including today
  hours weekly [-1]         Browse this week or a relative week (Monday–Sunday)
  hours weekly [-1] --plain Print a weekly report
  hours export day|week [+-n] [--stdout]
                            Copy TSV to clipboard, or print it with --stdout

Entries: - 1h Meeting with John
         - 15m Sending e-mails
         - 1h30m Project work

Storage: ~/hours/YYYY/MM/DD.md (override with HOURS_DIR)
Editor:  HOURS_EDITOR, VISUAL, EDITOR, then nvim/vim/vi/nano
         Neovim starts clean by default; HOURS_EDITOR=nvim uses your config
Weekly:  j/k select day; h/l change week; Enter edit; y copy week; t today; q quit
'''


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (['-h'], ['--help'], ['help']):
        print(HELP)
        return 0
    try:
        if args and args[0] == 'export':
            args.pop(0)
            stdout = '--stdout' in args
            if stdout:
                args.remove('--stdout')
            if not 1 <= len(args) <= 2 or args[0] not in ('day', 'week'):
                raise ValueError('Usage: hours export day|week [+-n] [--stdout]')
            weekly = args[0] == 'week'
            day = resolve_date(args[1] if len(args) == 2 else None, weekly=weekly)
            text = export_tsv(week_days(day) if weekly else [day])
            if stdout:
                sys.stdout.write(text)
            else:
                target = copy_clipboard(text)
                print(f'Sent {len(text.splitlines()) - 1} entries to {target}.')
        elif args and args[0] == 'weekly':
            args.pop(0)
            plain = '--plain' in args
            if plain:
                args.remove('--plain')
            if len(args) > 1:
                raise ValueError('Usage: hours weekly [+-n] [--plain]')
            start = resolve_date(args[0] if args else None, weekly=True)
            if plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
                print_week(start)
            else:
                weekly_ui(start)
        else:
            if len(args) > 1:
                raise ValueError('Usage: hours [+-n|-mon|-tue|...]')
            day = resolve_date(args[0] if args else None)
            print(edit_day(day))
        return 0
    except (ValueError, OSError, curses.error) as exc:
        print(f'hours: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
