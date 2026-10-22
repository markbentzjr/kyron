# Release Notes Template

Use this template when creating a new GitHub release. Copy this content and customize it for the specific version.

---

## Kyron [VERSION] - [DATE]

### What's New

[Brief 1-2 sentence summary of this release]

### Installation

**Quick install:**
1. Download `Kyron-2.0.apk` from the Assets section below
2. Install the APK on your Android device
3. Open Kyron and start browsing

**For detailed instructions:** See [INSTALL.md](https://github.com/markbentzjr/kyron/blob/main/INSTALL.md)

**System requirements:**
- Android 9.0 (API level 29) or later
- 20-30 MB free storage space
- Internet connection for initial sync and updates

### Changes in This Release

#### Added
- [Feature 1]
- [Feature 2]

#### Changed
- [Change 1]
- [Change 2]

#### Fixed
- [Bug fix 1]
- [Bug fix 2]

#### Data Updates
- [New places added]
- [Data quality improvements]
- [Geocoding coverage improvements]

### Known Issues

- [Known issue 1]
- [Known issue 2]

### Upgrading from Previous Version

- Your favorites, alerts, and settings will be preserved automatically
- No action required - just install the new APK

### Data Sources

This release includes data from:
- **JCDH** (Jefferson County Dept. of Health) - Jefferson County
- **ADPH** (Alabama Dept. of Public Health) - 65 Alabama counties
- **MCHD** (Mobile County Health Dept.) - Mobile County

Total places in bundled dataset: [NUMBER]

### Verification

**APK information:**
- File size: [SIZE] MB
- SHA-256: [CHECKSUM]
- Package: com.kyronapp.kyron
- Version code: [VERSION_CODE]
- Min SDK: 29 (Android 9.0)
- Target SDK: 34 (Android 14)

You can verify the SHA-256 checksum of the downloaded APK:
- **Linux/Mac:** `shasum -a 256 Kyron-2.0.apk`
- **Windows (PowerShell):** `Get-FileHash Kyron-2.0.apk -Algorithm SHA256`

### Privacy and Security

- No accounts or sign-up required
- All data stored locally on your device
- No telemetry or analytics
- No data sent to third parties
- Network access only for fetching public health department data

See [SECURITY.md](https://github.com/markbentzjr/kyron/blob/main/SECURITY.md) for details.

### Getting Help

- **Installation issues:** See [INSTALL.md](https://github.com/markbentzjr/kyron/blob/main/INSTALL.md)
- **Troubleshooting:** Check [INSTALL.md](https://github.com/markbentzjr/kyron/blob/main/INSTALL.md#troubleshooting)
- **Report bugs:** [Open an issue](https://github.com/markbentzjr/kyron/issues/new)
- **Feature requests:** [Open an issue](https://github.com/markbentzjr/kyron/issues/new)

### Acknowledgments

- Health inspection data provided by Jefferson County Dept. of Health, Alabama Dept. of Public Health, and Mobile County Health Dept.
- Map tiles from OpenStreetMap and contributors
- Built with Kotlin, AndroidX, and open-source libraries

---

## Changelog

For a complete history of changes, see [CHANGELOG.md](https://github.com/markbentzjr/kyron/blob/main/CHANGELOG.md).
