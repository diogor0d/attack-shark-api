# Security policy

## Supported code

Security fixes are applied to the latest code on the default branch. This project has not
yet published versioned releases with separate maintenance windows.

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** feature
for this repository. Do not open a public issue containing exploit details, raw USB captures,
credentials, or personally identifying information.

Include the affected revision, a concise reproduction, expected and observed behavior, and
any relevant sanitized logs. Remove unrelated USB traffic and input data from all evidence.

## Security boundary

The API is designed for a single Windows user and binds to `127.0.0.1` by default. It does
not provide authentication or authorization for remote clients. Running it on a LAN address,
behind a public reverse proxy, or through a tunnel is outside the supported security model.

The service intentionally rejects unverified hardware revisions and commands related to
firmware, reset, bootloader, calibration, flash erase, macros, keymaps, and Hall-effect
configuration. Static per-key patterns are the only supported flash-backed operation and
require explicit acknowledgement plus write-rate limiting.

Raw USB captures can contain traffic from unrelated devices. They must remain outside Git;
only minimal sanitized protocol fixtures may be committed.
