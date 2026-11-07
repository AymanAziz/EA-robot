# Verified daily macOS backups

The macOS backend can run `scripts/backup.py` once a day through the per-user
`com.papertrade.backup` LaunchAgent. The supplied template targets the dedicated
`var/daily-backups` directory, retains seven verified generations, and bounds the
direct `var/*-launchd.log` files at 5 MiB with three rotated copies.

Replace every `__PROJECT_DIR__` placeholder in
`deploy/com.papertrade.backup.plist.template` with the absolute repository path,
write the result to `~/Library/LaunchAgents/com.papertrade.backup.plist`, and
validate it before loading:

```bash
plutil -lint ~/Library/LaunchAgents/com.papertrade.backup.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.papertrade.backup.plist
launchctl kickstart -k "gui/$(id -u)/com.papertrade.backup"
```

The job uses SQLite's online backup API and verifies `PRAGMA integrity_check` for
each copied database. It copies model artifacts, records byte sizes and SHA-256
digests in `manifest.json`, verifies the staged generation, publishes it with one
rename, and only then removes verified generations beyond the retention count.
Unrecognized files or directories in the destination are never retention targets.
The mode-0600 `var/backup-status.json` records `ok` plus the retained count, or an
error type without exception text. Standard output and errors go to
`var/backup-launchd.log`.

Log rotation uses copy-and-truncate so launchd children retain the active file
inode. It examines only regular, non-symlink files directly matching
`var/*-launchd.log`; it does not recurse or touch other log names.

Each SQLite file is an individually consistent online snapshot. The daily job is
not a claim that `papertrade.db` and `simulator.db` share one atomic instant. Before
an upgrade, migration, or recovery cutover, pause entries, confirm zero or protected
positions, stop the API and scheduler writers, and create an additional coordinated
backup.

To test recovery, keep writers stopped, copy one generation to a temporary state
directory (excluding `manifest.json`), run `PRAGMA integrity_check` on every copied
database, start against that isolated state, and reconcile paper-broker truth before
allowing entries. The automated test suite performs this core restore check by
opening the generated database and reading preserved application evidence.
