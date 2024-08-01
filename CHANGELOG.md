# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


<!--
## [Unreleased]
-->

## [0.5.1] - 2024-08-01

### Fixed

- lpc43xx: Do not detach.
- lpc43xx: Format flash image header in little-endian.


## [0.5.0] - 2024-07-24

### Added

- Add changelog.

### Fixed

- Use timeout instead of delay after DFU_DETACH.
- Set configuration after, not before attempting to detach kernel driver.


## [0.4.0] - 2024-07-04

### Added

- Initial release.


[Unreleased]: https://github.com/greatscottgadgets/pyfwup/compare/0.5.1...HEAD
[0.5.1]: https://github.com/greatscottgadgets/pyfwup/compare/0.5.0...0.5.1
[0.5.0]: https://github.com/greatscottgadgets/pyfwup/compare/0.4.0...0.5.0
[0.4.0]: https://github.com/greatscottgadgets/pyfwup/releases/tag/0.4.0
