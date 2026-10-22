# Installing Kyron on Android

This guide explains how to download and install Kyron on your Android phone from GitHub releases.

## Quick Start

1. Go to the [Kyron Releases page](https://github.com/markbentzjr/kyron/releases)
2. Download the latest `Kyron-2.0.apk` file
3. Install the APK on your Android device
4. Open Kyron and start browsing restaurant health scores

## Detailed Instructions

### Step 1: Download the APK

#### From Your Android Phone (Recommended)

1. Open your web browser on your Android phone
2. Navigate to: `https://github.com/markbentzjr/kyron/releases`
3. Tap on the latest release (the one at the top with the highest version number)
4. Scroll down to the "Assets" section
5. Tap on `Kyron-2.0.apk` to download it
6. Wait for the download to complete (file size is approximately 6-7 MB)

#### From Your Computer

1. Open your web browser on your computer
2. Navigate to: `https://github.com/markbentzjr/kyron/releases`
3. Click on the latest release
4. Scroll down to the "Assets" section
5. Click on `Kyron-2.0.apk` to download it
6. Transfer the APK file to your Android phone (USB cable, cloud storage, email, etc.)

### Step 2: Enable Installation from Unknown Sources

Before you can install the APK, you need to allow your phone to install apps from sources other than the Google Play Store.

**Note:** The exact steps vary by Android version and phone manufacturer. These are general instructions.

#### For Android 13 and later:

1. Open your phone's **Settings** app
2. Go to **Security & privacy** (or **Security**)
3. Tap on **Install unknown apps** (or **Unknown sources**)
4. Find your web browser (Chrome, Firefox, etc.) in the list
5. Tap on it and enable **Allow from this source**

#### For Android 8–12:

1. Open your phone's **Settings** app
2. Go to **Apps & notifications** (or **Apps**)
3. Tap on **Special app access** (or **Advanced** > **Special app access**)
4. Tap on **Install unknown apps**
5. Find your web browser and enable it

#### For Android 7 and earlier:

1. Open your phone's **Settings** app
2. Go to **Security**
3. Enable **Unknown sources** (or **Allow installation from unknown sources**)

### Step 3: Install the APK

#### If you downloaded on your phone:

1. Open your **Files** app (or **Downloads** app)
2. Navigate to your **Downloads** folder
3. Tap on `Kyron-2.0.apk`
4. You may see a warning about installing from unknown sources - tap **Install anyway** or **Settings** to allow it
5. Wait for the installation to complete
6. Tap **Open** or **Done**

#### If you downloaded on your computer:

1. Transfer the APK file to your phone (USB, cloud storage, email, etc.)
2. On your phone, open your **Files** app
3. Navigate to where you saved the APK
4. Tap on `Kyron-2.0.apk`
5. Follow the same installation steps as above

### Step 4: First Launch

1. Tap the **Kyron** icon in your app drawer
2. You'll see a welcome dialog explaining the app's features
3. Tap **Start exploring** to begin
4. The app will load the bundled Alabama restaurant data (this may take a few seconds)
5. Browse, search, or use the map to find restaurant health scores

## Troubleshooting

### "Install blocked" or "Unknown sources" error

**Problem:** Your phone is blocking installation from unknown sources.

**Solution:**
- Follow Step 2 above to enable installation from unknown sources for your browser
- Make sure you're using the browser you enabled (not a different app)

### "Package parse error" or "There was a problem parsing the package"

**Problem:** The APK file may be corrupted or incomplete.

**Solution:**
- Delete the downloaded APK and download it again
- Make sure the download completed fully (check file size is ~6-7 MB)
- Try downloading from a different browser or from your computer

### "App not installed" error

**Problem:** An older version of Kyron may already be installed.

**Solution:**
- Go to **Settings** > **Apps** > **Kyron**
- Tap **Uninstall**
- Try installing the new APK again

### "Insufficient storage" error

**Problem:** Your phone doesn't have enough storage space.

**Solution:**
- Free up space by deleting unused apps or files
- Kyron requires approximately 20-30 MB of free space for installation and data

### Maps not showing pins

**Problem:** The map view doesn't show restaurant pins.

**Solution:**
- Make sure you have an internet connection (maps tiles are downloaded on demand)
- Zoom in to an area with restaurants
- Some restaurants don't have verified addresses and won't show pins (they're still in Browse)

### App crashes on launch

**Problem:** The app crashes immediately after opening.

**Solution:**
- Make sure you're running Android 9 (API level 29) or later
- Clear the app data: **Settings** > **Apps** > **Kyron** > **Storage** > **Clear data**
- Uninstall and reinstall the app
- Report the issue on GitHub with your Android version and phone model

## Permissions

Kyron requires the following permissions:

- **Internet:** To fetch restaurant health inspection data from official health department websites
- **Network state:** To check if you have an internet connection
- **Notifications:** To send you alerts when your favorite places receive new inspection scores
- **Location (coarse and fine):** To set your home location for area alerts and to show your position on the map
- **Wake lock:** To run background sync when your phone is asleep
- **Boot completed:** To schedule background sync after your phone restarts

All permissions are justified and necessary for the app's functionality. Kyron does not collect, transmit, or sell your personal data.

## Data Usage

- **Initial download:** The APK is approximately 6-7 MB
- **First launch:** The app loads bundled data (~8 MB) from the APK itself (no additional download)
- **Background sync:** Approximately 1-2 MB every 12 hours when syncing with health department sources
- **Map tiles:** Downloaded on demand when viewing the map (typically a few MB per area viewed)

Kyron is designed to work well even on limited data plans. You can disable background sync in the Alerts tab if you prefer to sync manually.

## Updates

To update Kyron to a new version:

1. Download the new APK from the [Releases page](https://github.com/markbentzjr/kyron/releases)
2. Install it (it will automatically update the existing installation)
3. Your favorites, alerts, and settings will be preserved

## Uninstalling

To uninstall Kyron:

1. Open **Settings** > **Apps** > **Kyron**
2. Tap **Uninstall**
3. Confirm the uninstall

**Note:** Uninstalling will delete all app data including your favorites and alert settings. Back up your data from the Alerts tab before uninstalling if you want to preserve it.

## Safety and Security

### Is the APK safe to install?

Yes. The APK is built from the public source code on GitHub and does not contain:
- Malware or spyware
- Hidden trackers or analytics
- Unnecessary permissions
- Adware or monetization gates

You can verify the source code at: https://github.com/markbentzjr/kyron

### Why isn't Kyron on the Google Play Store?

Kyron is currently distributed via GitHub because:
- It's in active development and not yet ready for Play Store submission
- Play Store submission requires a $25 one-time fee and additional compliance work
- GitHub distribution allows for faster iteration and community feedback

Future plans include Play Store submission once the app is more mature (see the [2.0 Blueprint](docs/Kyron-2.0-Blueprint.md)).

### What data does Kyron collect?

Kyron is designed to be privacy-focused and local-first:
- All data is stored on your device
- No accounts or sign-up required
- No telemetry or analytics
- No data is sent to third parties
- Network access is only for fetching public health department data

See the [Security Policy](SECURITY.md) for more details.

## System Requirements

- **Android version:** 9.0 (API level 29) or later
- **Storage:** 20-30 MB free space
- **Internet:** Required for initial data sync and background updates (works offline after first sync)
- **GPS:** Optional (for location-based alerts and map positioning)

## Getting Help

If you encounter issues not covered in this guide:

1. Check the [Troubleshooting section](#troubleshooting) above
2. Search existing [GitHub Issues](https://github.com/markbentzjr/kyron/issues)
3. [Open a new issue](https://github.com/markbentzjr/kyron/issues/new) with:
   - Your Android version
   - Your phone model
   - A detailed description of the problem
   - Steps to reproduce the issue

## Alternative Installation Methods

### From Source Code

If you're a developer and want to build Kyron from source:

1. Clone the repository: `git clone https://github.com/markbentzjr/kyron.git`
2. Follow the build instructions in [CONTRIBUTING.md](CONTRIBUTING.md)
3. Install the resulting APK on your device

### F-Droid (Future)

There are plans to submit Kyron to F-Droid, an open-source app repository. This would provide automatic updates through the F-Droid client app. Check the repository for updates on this.

## Verification

To verify the authenticity of the APK:

1. Check that the APK is signed with the Kyron debug key (this will change to a release key when ready for Play Store)
2. Compare the file size with the size listed in the GitHub release
3. Verify the APK's SHA-256 checksum (provided in the release notes) matches your downloaded file

On Android, you can verify the signature with:
```bash
apksigner verify --print-certs Kyron-2.0.apk
```

On Linux/Mac, you can check the SHA-256 with:
```bash
shasum -a 256 Kyron-2.0.apk
```

On Windows (PowerShell):
```powershell
Get-FileHash Kyron-2.0.apk -Algorithm SHA256
```

## What's Next?

After installing Kyron:

1. **Browse restaurants:** Search for places or filter by county and score
2. **Check the map:** See restaurant locations with color-coded score pins
3. **Read violation details:** Tap a place to see why it got its score (Jefferson County only)
4. **Watch favorites:** Star places you care about to get alerts
5. **Set up area alerts:** Get notified when new low scores appear near you
6. **Explore other states:** Download region packs for Florida, Georgia, and more (from the Coverage tab)

For more information about Kyron's features, see the [README](README.md).
