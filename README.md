A TUI for tracking hours in Markdown format.

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

Hours are written as Markdown lists to `~/hours/YYYY/MM/DD.md`

```markdown
- 1h Meeting with John
- 15m Sending e-mails
- 1h30m Project work
```

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
