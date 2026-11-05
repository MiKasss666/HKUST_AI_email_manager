# Privacy Policy — Email Manager Dify plugin

This plugin talks to **Microsoft Graph** on behalf of the person who signs in,
and stores its own runtime state in **Dify's plugin persistent storage** (scoped
to the Dify workspace that installed the plugin). It does not send data to any
other service that the plugin controls.

## What is accessed

With the delegated permissions the user approves during device-code sign-in:

- `Mail.ReadWrite` — read inbox messages (subject, sender, body, categories) and
  write the S/A/B/C/Sum categories and the urgent flag back to those messages;
- `Mail.Send` — send the summary report or an alert e-mail to the address the
  user configured;
- `offline_access`, `openid`, `profile`, `User.Read` — keep the sign-in alive and
  read the signed-in account name.

The plugin only touches messages in the signed-in user's own mailbox. It never
creates, deletes or reads the Outlook master category list, never sends mail to
third parties, and never attaches message bodies to anything other than the
workflow's LLM node (which the Dify workspace owner configured).

## What is stored

In Dify plugin storage (workspace scoped, not shared between workspaces):

- OAuth access token, refresh token, expiry and account name;
- a pending device code while sign-in is in progress;
- runtime state: baseline message id, failed round counter, ids of messages
  judged "not school mail", lock timestamps, pause flag and the last catch-up /
  report timestamps.

Tokens and state are not written to logs by the plugin. Removing the plugin or
signing out (`auth_sign_out` tool) deletes the stored credential.

## What is sent where

- Microsoft Graph receives the Graph API requests (read / PATCH / sendMail).
- The e-mail content that the Dify workflow sends to its configured model
  provider is controlled by the workflow (LLM nodes), not by this plugin. If a
  school-provided AI endpoint is configured in Dify, message bodies go there.

The plugin does not collect analytics, telemetry or crash reports.
