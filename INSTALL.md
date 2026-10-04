# Install Zot Relay

For a local agent whose client supports stdio MCP. Zotero desktop must be on
the same computer. Setup must leave the library unchanged.

This flow is a local preview, tested on macOS. The public guide will be
available after the new repository is created and these changes are on GitHub.
For now, use the user-supplied checkout.

## Install

Install this repository in a persistent Python environment. With uv:

```console
uv tool install --python 3.12 --exclude-newer "1 week" /absolute/path/to/source.zip
```

Use a source archive pinned to a commit of
[akshithg/zot-relay](https://github.com/akshithg/zot-relay), a release wheel from that repository,
or the supplied local checkout. Resolve the main commit through
`https://api.github.com/repos/akshithg/zot-relay/commits/main` and download
`https://github.com/akshithg/zot-relay/archive/COMMIT_SHA.zip`. Read this guide from
the same source. Distribution stays on GitHub; use the archive or wheel,
not a package registry.

If uv is missing, use [Astral’s installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
uv can provide Python. A disposable `uvx` environment or editable checkout
is unsuitable for a persistent MCP connection.

## Configure and verify

Run `zot-relay-setup prepare` from the executable directory reported by
`uv tool dir --bin`. It returns the stdio server definition, the matching
plugin path, and its version as JSON. It does not edit client settings.

Configure the current client using that definition and its own MCP setup
instructions. Preserve other settings, back up files before editing, and update
the existing Zot Relay entry rather than adding duplicates. If migrating from
`zev`, replace that entry with `zot-relay`; do not leave both connections active.
Use the absolute server command returned by the helper.

With Zotero open, run `zot-relay-setup check`. A successful check means the matching
bridge is already running. Follow any reported error; if the plugin is missing
or its version differs, install the returned plugin through
**Zotero → Tools → Plugins**, restart Zotero, and check again. Use computer
access when available; otherwise ask the user to complete that plugin step.
Do not copy XPIs into profile directories.

Reload the client’s MCP connections as needed. If a restart is required, leave
it to the user after this conversation. Verify that the actual client discovers
`eval_zotero` and can run:

```js
return JSON.stringify({ok: true, zoteroVersion: Zotero.version});
```

Report the installed version or source commit, verification result, backup
location, and any remaining user action. Do not report success if client
verification is pending. Keep Zotero open during use.

## Updates and removal

Repeat installation and verification to update. For removal, disable Zot Relay in
the client, remove **Zot Relay Bridge** through Zotero’s Plugins window, and run
`uv tool uninstall zot-relay`. Retain settings backups unless asked to remove them.
