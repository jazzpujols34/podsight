# Cron Setup for Gooaye Episode Auto-Check

股癌 typically releases new episodes on **Wednesday** and **Saturday**.

This guide shows how to schedule `auto_check_new_episodes.py` to run at 21:00 on these days.

## macOS: Using launchd

### 1. Create the plist file

```bash
# Create the LaunchAgents directory if it doesn't exist
mkdir -p ~/Library/LaunchAgents
```

Create `~/Library/LaunchAgents/com.gooaye.autocheck.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gooaye.autocheck</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>/Users/YOUR_USERNAME/path/to/gooaye_pipeline/auto_check_new_episodes.py</string>
        <string>--notify</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <!-- Wednesday at 21:00 -->
        <dict>
            <key>Weekday</key>
            <integer>3</integer>
            <key>Hour</key>
            <integer>21</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Saturday at 21:00 -->
        <dict>
            <key>Weekday</key>
            <integer>6</integer>
            <key>Hour</key>
            <integer>21</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>ANTHROPIC_API_KEY</key>
        <string>YOUR_API_KEY_HERE</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/path/to/gooaye_pipeline</string>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/path/to/gooaye_pipeline/logs/autocheck.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/path/to/gooaye_pipeline/logs/autocheck.error.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 2. Update paths in the plist

Replace:
- `YOUR_USERNAME` with your macOS username
- `/path/to/gooaye_pipeline` with the actual path
- `YOUR_API_KEY_HERE` with your Anthropic API key

### 3. Create logs directory

```bash
mkdir -p /path/to/gooaye_pipeline/logs
```

### 4. Load the agent

```bash
# Load the agent
launchctl load ~/Library/LaunchAgents/com.gooaye.autocheck.plist

# Verify it's loaded
launchctl list | grep gooaye

# Test run manually
launchctl start com.gooaye.autocheck
```

### 5. Manage the agent

```bash
# Stop the agent
launchctl stop com.gooaye.autocheck

# Unload (disable)
launchctl unload ~/Library/LaunchAgents/com.gooaye.autocheck.plist

# Reload after changes
launchctl unload ~/Library/LaunchAgents/com.gooaye.autocheck.plist
launchctl load ~/Library/LaunchAgents/com.gooaye.autocheck.plist
```

---

## Linux: Using crontab

### 1. Edit crontab

```bash
crontab -e
```

### 2. Add the cron entry

```cron
# Gooaye episode auto-check: Wed & Sat at 21:00
# m h dom mon dow command
0 21 * * 3,6 cd /path/to/gooaye_pipeline && /usr/bin/python3 auto_check_new_episodes.py >> logs/autocheck.log 2>&1

# With environment variables
0 21 * * 3,6 ANTHROPIC_API_KEY=your_key_here cd /path/to/gooaye_pipeline && /path/to/venv/bin/python auto_check_new_episodes.py >> logs/autocheck.log 2>&1
```

### 3. Explanation

```
0 21 * * 3,6
│ │  │ │ │
│ │  │ │ └── Day of week (3=Wed, 6=Sat)
│ │  │ └──── Month (any)
│ │  └────── Day of month (any)
│ └───────── Hour (21:00)
└──────────── Minute (0)
```

### 4. Alternative: Using a wrapper script

Create `/path/to/gooaye_pipeline/run_autocheck.sh`:

```bash
#!/bin/bash

# Load environment
source /path/to/gooaye_pipeline/.env

# Activate virtual environment
source /path/to/gooaye_pipeline/venv/bin/activate

# Change to project directory
cd /path/to/gooaye_pipeline

# Run the script
python auto_check_new_episodes.py

# Log completion
echo "$(date): Auto-check completed" >> logs/autocheck.log
```

Make it executable:

```bash
chmod +x /path/to/gooaye_pipeline/run_autocheck.sh
```

Crontab entry:

```cron
0 21 * * 3,6 /path/to/gooaye_pipeline/run_autocheck.sh >> /path/to/gooaye_pipeline/logs/autocheck.log 2>&1
```

### 5. Using systemd timer (alternative to cron)

Create `/etc/systemd/user/gooaye-autocheck.service`:

```ini
[Unit]
Description=Gooaye Episode Auto-Check

[Service]
Type=oneshot
WorkingDirectory=/path/to/gooaye_pipeline
Environment="ANTHROPIC_API_KEY=your_key_here"
ExecStart=/path/to/venv/bin/python auto_check_new_episodes.py
```

Create `/etc/systemd/user/gooaye-autocheck.timer`:

```ini
[Unit]
Description=Run Gooaye auto-check on Wed & Sat at 21:00

[Timer]
OnCalendar=Wed,Sat 21:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user enable gooaye-autocheck.timer
systemctl --user start gooaye-autocheck.timer
```

---

## Testing

### Manual test

```bash
cd /path/to/gooaye_pipeline
python auto_check_new_episodes.py --dry-run
```

### Verify cron is working

```bash
# Check cron logs (Linux)
grep CRON /var/log/syslog | tail -20

# Check launchd logs (macOS)
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep gooaye
```

---

## Troubleshooting

### Script doesn't run

1. Check paths are absolute (not relative)
2. Verify Python path: `which python3`
3. Ensure API key is set correctly
4. Check log files for errors

### Permission issues

```bash
# Make script executable
chmod +x auto_check_new_episodes.py

# Check crontab permissions
ls -la /var/spool/cron/crontabs/
```

### Environment variables not loaded

For cron, environment is minimal. Either:
1. Set variables inline in the cron entry
2. Source `.env` in a wrapper script
3. Use full paths for everything

### macOS sleep issues

If your Mac sleeps during scheduled time, add to plist:

```xml
<key>StartCalendarInterval</key>
<!-- ... -->
<key>AbandonProcessGroup</key>
<true/>
```

Or use `caffeinate` in the command to prevent sleep during execution.
