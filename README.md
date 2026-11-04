# CodeZ Manager

A Discord bot for server moderation, tickets, and staff team management.

## Setup

1. Copy `.env.example` to `.env` and fill in your own bot token and owner IDs.
   Never share or commit your real `.env` file — the token is a secret.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```
   python main.py
   ```

## Prefix

The default prefix is `Cz!` and is case-insensitive — `cz!`, `Cz!`, and `CZ!`
all work. You can change it by setting `PREFIX` in your `.env` file.

## Notes on this build

- No emojis are used anywhere in this bot — not custom Discord emojis, not
  unicode emojis. Status indicators use plain text/words instead.
- The bot needs the **Server Members**, **Message Content**, and
  **Presence** privileged intents enabled in the Discord Developer Portal
  for member tracking, moderation, and online/offline status features to
  work.

## Feature overview

### Tickets
- `Cz!ticket panel` — posts a panel with an "Open Ticket" button.
- `Cz!ticket category <#category>` — where new ticket channels are created.
- `Cz!ticket role <@role>` — support role that can see/manage tickets.
- `Cz!ticket logs <#channel>` — where closed-ticket transcripts are posted.
- `Cz!ticket close` — closes the current ticket channel.
- Each ticket channel gets Claim/Unclaim and Close Ticket buttons.

### Team Setup (all commands are owner only)
Shows which staff are available right now in a single panel, like:

    Available Support      (online / idle / do not disturb)
    Unavailable Support    (offline / invisible)
    Don't ping unavailable support members.
    Updated 3 minutes ago

- `Cz!teamsetup @role [@role ...]` — track existing roles as staff roles.
  The role IDs are saved in the database. No roles are ever created.
- `Cz!teampanel <#channel>` — post the panel in that channel.
- `Cz!teamrefresh` — force the panel to update right now.
- `Cz!teamroles` — list currently tracked roles.
- `Cz!teamremoverole <@role>` — stop tracking a role.

**One message per day.** The bot posts one panel message and edits it whenever a
staff member goes online/offline, until the day ends (UTC midnight). The next
day it posts a fresh message and edits that one instead.

**Custom emojis** (optional, max 3) go in `emojis.json`:
`TEAM_AVAILABLE`, `TEAM_UNAVAILABLE`, `TEAM_WARNING`. Leave blank for none.

### Bot Access (owner only)
Give trusted people access to the bot's action commands without giving them
Discord permissions or any control over settings.
- `Cz!botaccess add <@user or id>` — give a user access.
- `Cz!botaccess remove <@user or id>` — remove their access.
- `Cz!botaccess list` — show everyone with access.

People on the list **can** use: `kick`, `ban`, `unban`, `mute`, `unmute`,
`purge`, `warn`, `warnings`, `clearwarnings`, `say`, `join`, `leave`,
`suggest moderate`, `tracker refresh`, plus read-only commands.

People on the list **cannot**: set or clear limits (`user limit ...`), run any
`teamsetup*`, `greet`, `ticket`, `feedback`, `tracker add/remove/panel/alertchannel`,
`suggest setchannel/logchannel/threshold`, `tag`, or `botaccess` itself.

They are still subject to per-user daily limits and the role hierarchy (they
cannot act on someone with an equal or higher role). `say` from a
non-owner cannot ping `@everyone`, `@here`, or roles.

### Moderation
- `Cz!ban @user [reason]`, `Cz!kick @user [reason]`,
  `Cz!mute @user [duration] [reason]` (duration like `10m`, `1h`, `2d`),
  `Cz!unban <user id>`, `Cz!unmute @user`.
- `Cz!warn @user [reason]`, `Cz!warnings @user`, `Cz!clearwarnings @user`.
- `Cz!purge <amount> [@user]`.
- `Cz!say [#channel] <message>` — administrators only.

### Per-user daily moderation limits
The bot owner can cap how many times a specific staff member may use
ban/kick/mute per rolling 24-hour period:
- `Cz!user limit set ban @user 2` — that user can ban at most 2 people/day.
- `Cz!user limit set kick @user 5`
- `Cz!user limit set mute @user 10`
- `Cz!user limit show @user` — see their limits and today's usage.
- `Cz!user limit clear ban @user` — remove a limit.

Server owners and configured bot owners always bypass limits.

### Application Emojis (slash commands, owner only)
Upload images as the bot's own application emojis and wire them into
`emojis.json` slots (`TEAM_AVAILABLE`, `SUCCESS`, or any custom slot you use
in your own code via `codezmanager.emojis.E["SLOT"]`).
- `/emoji upload slot:<SLOT> name:<name> image:<file>` — uploads the image to
  Discord as an application emoji and assigns it to that slot.
- `/emoji assign slot:<SLOT> emoji:<existing emoji>` — points a slot at an
  emoji that's already uploaded, instead of uploading a new one.
- `/emoji list` — shows every slot with an assigned emoji.
- `/emoji remove slot:<SLOT>` — clears a slot's assignment (keeps the emoji
  uploaded to Discord).
- `/emoji sync slot:<SLOT>` — deletes the emoji from Discord entirely and
  clears its slot.

Assignments are stored in `db/emojimanager.db` and mirrored into
`emojis.uploaded.json`, which always takes priority over the fallback
literals in `emojis.json`.

### About (slash commands)
Shows the server's staff, grouped into categories you define, each backed by
a Discord role — anyone with that role appears under it automatically.
- `/about` — posts a paginated staff list with `<` / `>` buttons.
- `/aboutsetup addcategory label:<name> role:<@role>` — add or update a
  category (owner only). Order shown matches the order categories were added.
- `/aboutsetup removecategory label:<name>` — remove a category (owner only).
- `/aboutsetup listcategories` — list configured categories and their roles.

Categories with nobody in the role show **Vacant**. Data is stored in
`db/emojimanager.db`, per server.

### Slash command sync
On startup the bot syncs its slash commands (`/about`, `/aboutsetup`,
`/emoji`). By default this syncs **globally**, which can take up to an hour
to show up in Discord the first time. Set `SLASH_SYNC_GUILD_ID` in `.env` to
one server ID while testing to get instant syncing in that server only.

### Everything else
Greet/welcome messages, suggestions, feedback, bot-status tracking,
voice-stay, and the display-name style tool (`tag`) are unchanged from the
original bot aside from the renaming and emoji removal. Run `Cz!help` in
your server for the full, up-to-date command list.
