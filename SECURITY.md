# Security

## Reporting

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting for this repository.

## Scope

Burn runs only on the local Mac and binds its server to `127.0.0.1`. It reads Cursor's local session during a sync and does not persist the access token. The cache is stored under the current user's Application Support directory with owner-only permissions.

The beta is ad-hoc signed and not notarized. Verify the downloaded archive against the SHA-256 file attached to the release.
