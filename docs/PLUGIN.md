# Email Manager — Dify plugin

A Microsoft Graph tool plugin for the **AI Email Manager** Dify workflow. It
replaces the mailbox/authentication/state layer of the original Windows desktop
app (`Email_manager_beta` v3.0.0) so the whole system can run inside Dify.

This package is intended to be installed **after** the companion workflow
(`workflows/email-manager-main.yml`) or together with it. It is a *tool* plugin:
all decisions, prompts and report HTML live in the Dify workflow.

## Features

| Tool | Purpose |
|---|---|
| `auth_status` / `auth_start` / `auth_poll` / `auth_sign_out` | Microsoft **device-code** sign-in. No Entra app registration, client secret, redirect URI or admin consent needed. |
| `check` | Read-only self check (account, inbox size, token lifetime). |
| `collect` | One inbox scan: headers only, skip processed/control mail, download bodies for ≤30 candidates, return pending `sum` commands and untagged reports. |
| `collect_recent` | Read recently classified mails (S/A/B/C) for the summary report. |
| `apply` | Write categories back: merge (keep the user's own labels), flag urgent S mail, skip non-school mail and remember its id. |
| `tag` | Add `Sum` to command/report mails. |
| `send_report` | Send the HTML summary / alert mail. |
| `state_get` / `state_lock` / `state_unlock` / `state_advance` / `state_set` | Persistent watcher state: baseline, failed rounds, ignored ids, lock, pause flag. |

## Sign-in (device code)

The plugin uses the same fallback strategy as the original app:

1. an optional `client_id` passed by the workflow (environment variable);
2. otherwise the well-known Microsoft public clients:
   `Microsoft Graph Command Line Tools`, `Azure CLI`, `Azure PowerShell`.

The workflow calls `auth_start`, shows the returned `user_code` and
`verification_uri` to the user, the user approves the delegated permissions in a
browser, then `auth_poll` stores the tokens. No Azure portal work is required.
The user only consents once per account.

> If the school tenant forbids user consent for these public clients, the
> sign-in cannot be completed without administrator approval. This is the same
> limitation as the original desktop app.

## Build & install

Prerequisites: Python 3.12 and the Dify plugin CLI
(`dify-plugin-daemon` release, `dify` executable).

```bash
dify plugin package ./email_manager
```

This produces `email_manager.difypkg`. Install it in Dify:

- **From GitHub** (recommended for sharing): publish the plugin project in a
  public repository, attach the `.difypkg` to a GitHub Release, then
  *Integrations → Install → From GitHub* and paste the repo URL;
- **Local package file**: *Integrations → Install → Local package file*.

`manifest.yaml` → `author` must match the GitHub account that owns the
repository when installing from GitHub. Change `your-github-handle` accordingly
before packaging.

## Limitations

- Microsoft may change the availability of the public clients used for the
  device-code fallback; set `client_id` to your own public client if you can.
- The plugin state is workspace scoped. Run one Dify workspace per mailbox.
- A single workflow round handles at most 30 candidate mails (enforced by
  `collect`).
