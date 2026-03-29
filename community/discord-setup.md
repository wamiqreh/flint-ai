# Discord Server Setup Guide

This guide describes the recommended Discord server structure for the Flint community.

---

## Server Overview

**Server Name:** Flint  
**Server Icon:** Use the project logo  
**Server Banner:** A banner with the tagline: *"Queue-driven AI agent orchestration at scale"*

---

## Channel Structure

### Category: 📢 Information

| Channel | Purpose | Permissions |
|---------|---------|-------------|
| `#welcome` | Welcome message, rules, role selection, getting-started links | Read-only for members |
| `#announcements` | Release announcements, breaking changes, important updates | Read-only for members |
| `#rules` | Server rules and Code of Conduct reference | Read-only for members |

### Category: 💬 Community

| Channel | Purpose | Permissions |
|---------|---------|-------------|
| `#general` | General conversation about the project | Open |
| `#introductions` | New members introduce themselves | Open |
| `#off-topic` | Non-project conversations | Open |
| `#showcase` | Share what you've built with Flint | Open |

### Category: 🛠️ Development

| Channel | Purpose | Permissions |
|---------|---------|-------------|
| `#help` | Ask questions, get help with setup and usage | Open |
| `#contributing` | Discuss contributions, PRs, and development | Open |
| `#plugins` | Plugin development, submissions, and discussion | Open |
| `#architecture` | Deep dives into architecture decisions and design | Open |

### Category: 📦 Releases

| Channel | Purpose | Permissions |
|---------|---------|-------------|
| `#releases` | Automated release notifications from GitHub | Read-only (bot posts) |
| `#changelog` | Detailed changelog discussion | Open |

### Category: 🔧 Maintainers (Private)

| Channel | Purpose | Permissions |
|---------|---------|-------------|
| `#maintainer-chat` | Private maintainer discussion | Maintainers only |
| `#triage` | Issue triage and prioritization | Maintainers only |
| `#ci-alerts` | CI/CD failure notifications | Maintainers only |

---

## Roles

| Role | Color | Permissions | How to Get |
|------|-------|-------------|------------|
| **Admin** | Red | Full server management | Project owners |
| **Maintainer** | Orange | Manage messages, pin, manage threads | Appointed by admins |
| **Contributor** | Green | Access to contributor channels | Merged at least 1 PR |
| **Community** | Blue | Standard member access | Default role on join |
| **Bot** | Gray | Appropriate per-bot permissions | Automated |

### Role Assignment

- **Community** → Assigned automatically on join
- **Contributor** → Assigned manually by maintainers when a member's first PR is merged
- **Maintainer** → Appointed by admins based on sustained contribution

---

## Bot Recommendations

### 1. Welcome Bot — [MEE6](https://mee6.xyz/) or [Carl-bot](https://carl.gg/)

**Purpose:** Welcome new members, assign roles, moderate

**Setup:**
- Send a welcome DM with links to README, CONTRIBUTING.md, and docs
- Auto-assign the `Community` role on join
- Post a welcome message in `#welcome`

**Welcome Message Template:**
```
Welcome to the Flint community! 🎉

Here's how to get started:
📖 Read the docs: https://github.com/YOUR-ORG/flint-ai
🤝 Contribute: https://github.com/YOUR-ORG/flint-ai/blob/main/CONTRIBUTING.md
❓ Ask questions in #help
💡 Share ideas in #showcase

Please read #rules before participating. Happy building! 🚀
```

### 2. GitHub Integration — [GitHub Bot](https://support.discord.com/hc/en-us/articles/228383668)

**Purpose:** Post GitHub activity to Discord

**Setup:**
- Use Discord's native GitHub webhook integration or [GitHub-Discord Webhook](https://gist.github.com)
- Configure for the `flint-ai` repository

**Channel Routing:**

| Event | Channel |
|-------|---------|
| New release published | `#releases` |
| Issue opened | `#triage` (maintainers) |
| PR opened/merged | `#contributing` |
| CI failure | `#ci-alerts` (maintainers) |

### 3. Moderation — [Dyno](https://dyno.gg/) or [Carl-bot](https://carl.gg/)

**Purpose:** Auto-moderation, logging, anti-spam

**Setup:**
- Enable auto-mod for spam, excessive mentions, and invite links
- Log deleted messages and member join/leave events
- Set up slow mode on `#help` (1 message per 30 seconds)

### 4. Utility — [YAGPDB](https://yagpdb.xyz/)

**Purpose:** Custom commands, FAQ, role menus

**Setup:**
- Create a `!docs` command that links to documentation
- Create a `!issue` command that links to the issue tracker
- Create a `!contribute` command that links to CONTRIBUTING.md

---

## Moderation Guidelines

### Rules

Post these in `#rules`:

```
1. Be respectful — Follow our Code of Conduct.
2. Stay on topic — Use the appropriate channels.
3. No spam — No unsolicited promotions, ads, or repeated messages.
4. No NSFW — Keep content professional and appropriate.
5. English only — Primary language for all channels.
6. Search before asking — Check docs, issues, and existing messages first.
7. No DM harassment — Don't DM members without permission.
8. Use threads — For long conversations, use Discord threads.
```

### Enforcement Process

1. **First offense** → Friendly reminder of the rules
2. **Second offense** → Formal warning via DM
3. **Third offense** → Temporary mute (24 hours)
4. **Severe/repeated** → Temporary or permanent ban

### Moderation Actions

- Maintainers can delete messages, mute users, and create threads
- Admins can ban users and manage server settings
- All moderation actions should be logged (use bot logging)

---

## Step-by-Step Setup Instructions

### Step 1: Create the Server

1. Open Discord → Click the **+** icon → **Create My Own** → **For a club or community**
2. Name it **"Flint"**
3. Upload the project logo as the server icon
4. Enable **Community** features:
   - Server Settings → Enable Community → Follow the setup wizard
   - Set `#rules` as the rules channel
   - Set `#announcements` as the community updates channel

### Step 2: Create Categories and Channels

1. Create the categories listed above (📢 Information, 💬 Community, etc.)
2. Create each channel within its category
3. Set channel permissions:
   - `#welcome`, `#announcements`, `#rules` → Read-only for `@everyone`
   - `#maintainer-chat`, `#triage`, `#ci-alerts` → Visible only to Maintainer role
4. Set channel topics with brief descriptions

### Step 3: Create Roles

1. Server Settings → Roles → Create each role from the table above
2. Set role colors and permissions
3. Enable **role assignment** in `#welcome` using a bot or reaction roles

### Step 4: Set Up Bots

1. **Invite MEE6 or Carl-bot** → Configure welcome messages and auto-roles
2. **Set up GitHub webhook:**
   - In your GitHub repo → Settings → Webhooks → Add webhook
   - Use Discord's webhook URL for the appropriate channel
   - Select events: Releases, Issues, Pull Requests
3. **Invite Dyno or Carl-bot** → Configure auto-moderation rules
4. **Test all bots** in a private test channel first

### Step 5: Create the Welcome Message

Pin this message in `#welcome`:

```
👋 Welcome to the Flint community!

🔗 **Useful Links**
• GitHub: https://github.com/YOUR-ORG/flint-ai
• Docs: https://your-docs-site.dev
• Contributing: https://github.com/YOUR-ORG/flint-ai/blob/main/CONTRIBUTING.md
• Code of Conduct: https://github.com/YOUR-ORG/flint-ai/blob/main/CODE_OF_CONDUCT.md

📚 **Getting Started**
1. Read the #rules
2. Introduce yourself in #introductions
3. Ask questions in #help
4. Share your projects in #showcase

🏷️ **Roles**
React below to get your roles!
```

### Step 6: Invite Your Team

1. Create an invite link (never expires, unlimited uses)
2. Add the invite link to:
   - `README.md`
   - `CONTRIBUTING.md`
   - Project documentation site
   - GitHub repository description

### Step 7: Launch

1. Announce on GitHub Discussions
2. Add a Discord badge to the README
3. Monitor activity and adjust channels/permissions as the community grows

---

## Discord Badge for README

Add this to your `README.md`:

```markdown
[![Discord](https://img.shields.io/discord/YOUR_SERVER_ID?color=7289da&label=Discord&logo=discord&logoColor=white)](https://discord.gg/YOUR_INVITE_CODE)
```

---

## Tips for Growing the Community

- **Be responsive** — Answer questions quickly, especially early on
- **Celebrate contributions** — Announce merged PRs and new plugins
- **Run events** — Monthly community calls, hackathons, or showcase sessions
- **Create content** — Blog posts, tutorials, and video walkthroughs
- **Cross-promote** — Share on Twitter/X, Reddit, Hacker News, and dev communities
- **Empower contributors** — Promote active members to Contributor and Maintainer roles
