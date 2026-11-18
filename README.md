# hours

Track hours in Markdown with Neovim and a weekly terminal view.

## Setup

Clone the repo:

```sh
git clone https://github.com/joshnuss/hours.git ~/hours
cd ~/hours
```

Add this line to `~/.bashrc` or `~/.zshrc`, then open a new terminal:

```sh
export PATH="$HOME/hours:$PATH"
```

## Usage

```sh
hours                 # edit today
hours -1              # edit yesterday
hours -tue            # most recent Tuesday, including today
hours weekly          # this week (Monday–Sunday)
hours weekly -1       # last week
hours export day      # copy today for Google Sheets
hours export week -1  # copy last week
```

Enter your hours, then save with `:wq`:

```markdown
- 1h Meeting with John
- 15m Sending e-mails
- 1h30m Project work
```

Weekly keys: `j/k` select day, `h/l` change week, Enter edit, `y` copy, `t` today, `q` quit.

Files live in `~/hours/YYYY/MM/DD.md`. Set `HOURS_DIR` to change the location.

Neovim starts with a clean configuration. Set `HOURS_EDITOR=nvim` to use your own config, or choose another editor.
