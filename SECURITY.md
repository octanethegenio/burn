# Security

## Reporting

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting for this repository.

## Scope

Burn runs only on the local computer and binds its server to `127.0.0.1`. It reads Cursor's local session during a sync and does not persist the access token. The cache is stored in the current user's private application-data directory with owner-only permissions where the operating system supports Unix file modes.

Beta executables are not code-signed. Verify downloads against the SHA-256 files attached to each release.
