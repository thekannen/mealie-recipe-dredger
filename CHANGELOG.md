# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0-beta.6] - 2026-01-23
### Added
- **Paranoid Mode:** Integrated robust URL filtering and listicle detection to prevent non-recipe content from being imported.
- **Persistent Memory:** Added `rejects.json` and `imported.json` to track and skip bad or already processed URLs across container restarts.
- **Sitemap Discovery:** Improved sitemap detection using `robots.txt` parsing.
- **Resilience:** Implemented session-based retries with backoff for flaky network connections.

### Changed
- **Docker:** Standardized `container_name` to `mealie-recipe-dredger` and added volume mapping for persistent data.

## [1.0.0-beta.5] - 2026-01-15
### Fixed
- **Logging:** Resolved `NameError: name 'XMLParsedAsHTMLWarning' is not defined` that caused the container to crash on startup. (Thanks @rpowel and @johnfawkes!)
- **Stability:** Bulletproofed warning suppression logic to handle different BeautifulSoup4 versions.

## [1.0.0-beta.4] - 2026-01-12
### Added
- **Dependencies:** Included `lxml` in `requirements.txt` for faster, native XML sitemap parsing.
- **Documentation:** Restored release badges and sanitized README URLs.
