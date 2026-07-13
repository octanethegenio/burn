# Changelog

## 0.1.0-beta.7

- Added a prominent first-launch guide beside the macOS app in the download.

## 0.1.0-beta.6

- Packaged macOS as a double-clickable background launcher with no native window or Dock UI.
- Kept Windows packaging as a no-console executable that opens the browser directly.

## 0.1.0-beta.5

- Added per-event cache-read tokens to Recent events without crowding phone layouts.

## 0.1.0-beta.4

- Removed the first-run panel so the dashboard opens immediately.

## 0.1.0-beta.3

- Replaced the native macOS window with the user's default browser.
- Added a lightweight local launcher that opens Burn automatically and stops after the browser disconnects.
- Added Cursor session and private cache paths for macOS, Windows, and Linux.
- Added cross-platform packaging for macOS ARM/Intel, Windows x64, and Linux x64.
- Removed the obsolete Swift, WebKit, and macOS app-bundle build path.

## 0.1.0-beta.2

- Fixed narrow tables leaving unused space on the right in WebKit.
- Improved provider icon contrast in dark and light themes.
- Added Developer ID signing, notarization, and ticket stapling support to the former macOS build.

## 0.1.0-beta.1

- Added model and provider usage views, recent events, search, sorting, and themes.
- Added a short first-run onboarding screen.
- Fixed tables and controls for narrow screens.
- Moved the cache to the user's Application Support directory.
- Removed raw API payloads and unused account identifiers from local storage.
- Added atomic syncs, local endpoint protection, security headers, and private file permissions.
- Bundled fonts for offline use and removed unused starter assets.
- Added a lightweight native macOS shell and Apple Silicon beta build pipeline.
