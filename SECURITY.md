# Security Policy

## Supported Versions

Currently supported versions of Kyron will receive security updates as needed.

| Version | Supported | Security Updates |
|---------|-----------|------------------|
| 2.0.x   | Yes       | Yes              |
| 1.x     | No        | No               |

## Reporting a Vulnerability

If you discover a security vulnerability in Kyron, please report it responsibly.

**Do not open a public issue.** Instead, send your report privately to the project maintainer.

### How to Report

Send an email to the project maintainer with:
- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Any suggested fixes (if known)

The maintainer will acknowledge receipt within 48 hours and provide an estimated timeline for investigation and fix.

### What to Expect

- You will receive an acknowledgment of your report
- The maintainer will validate the vulnerability
- A fix will be developed and tested
- A security advisory will be published
- Credit will be given to the reporter (if desired)

## Security Guidelines for Contributors

### Never Commit Secrets

- **API keys:** Never commit API keys, tokens, or credentials to the repository
- **Passwords:** Never hardcode passwords or authentication credentials
- **Certificates:** Never commit signing certificates or private keys

### Input Validation

- **External data:** All data from health department sources must be validated
- **User input:** Sanitize all user input before processing
- **URL parameters:** Validate and sanitize any URL parameters

### Data Handling

- **User data:** Do not log or transmit user data without explicit consent
- **Sensitive logs:** Redact sensitive information from logs and error messages
- **Local storage:** Use Android's secure storage mechanisms for sensitive data

### Network Security

- **HTTPS only:** All network requests must use HTTPS
- **Certificate pinning:** Consider certificate pinning for critical endpoints
- **TLS verification:** Never disable TLS verification

### Dependencies

- **Review licenses:** Ensure all dependencies have compatible licenses
- **Update regularly:** Keep dependencies updated for security patches
- **Audit dependencies:** Periodically audit dependency security

## Current Security Practices

### Free/Open-Source Requirements

Kyron's default experience maintains these security and privacy principles:

1. **No mandatory accounts:** All features work without sign-up
2. **No telemetry:** No data collection or tracking without explicit consent
3. **Local-first:** User data stays on device by default
4. **No paid services:** Core functionality works without paid APIs
5. **Transparent networking:** All network requirements are documented

### API Key Policy

- **No embedded keys:** Production builds contain no API keys
- **Pipeline-only keys:** Geocoding keys are used only in the data pipeline, not in the app
- **User-provided keys:** If future features require keys, users provide them explicitly

### Data Sources

- **Official sources only:** Data comes from official health department websites
- **Read-only access:** No modification of source data
- **Rate limiting:** Scrapers respect rate limits (2 requests/second)
- **User-agent:** Uses identifiable user-agent for transparency

### Android Permissions

Current permissions (from AndroidManifest.xml):
- `INTERNET` - Fetching health department data
- `ACCESS_NETWORK_STATE` - Checking connectivity
- `POST_NOTIFICATIONS` - Alert notifications
- `ACCESS_COARSE_LOCATION` / `ACCESS_FINE_LOCATION` - User's home location for area alerts
- `WAKE_LOCK` - Background sync
- `RECEIVE_BOOT_COMPLETED` - Sync scheduling
- `FOREGROUND_SERVICE` - Background work

All permissions are justified and documented in the app's privacy policy.

### Data Storage

- **SQLite catalog:** Local database of places and inspections
- **User preferences:** Stored in SharedPreferences
- **User store:** Separate database for favorites, alerts, and user data
- **Backup rules:** Configured via `backup_rules.xml` and `data_extraction_rules.xml`

### Data Validation Gates

The build pipeline includes automated gates that prevent data quality issues:
- **Vector pathData validation:** Prevents malformed drawable crashes
- **Seed dataset validation:** Ensures all scores have valid place data
- **Canary completeness:** Verifies known establishments are present

## Known Security Considerations

### Web Scraping

Kyron scrapes public health department websites. This approach:
- Relies on page structure remaining stable
- Could break if sources change their formats
- Is mitigated by server-side monitoring and test fixtures

### Future Cloud Backend

The project plans for optional cloud sync (accounts, cross-device sync). When implemented:
- Will use a production-owned account (not personal test accounts)
- Will follow Firebase/Supabase security best practices
- Will maintain the local-first default experience
- Will require privacy policy and account deletion mechanisms

### Third-Party Libraries

Current dependencies include:
- AndroidX libraries (official Android components)
- OkHttp (networking)
- Jsoup (HTML parsing)
- osmdroid (OpenStreetMap maps)
- Kotlin coroutines

All are from reputable sources with active maintenance.

## Security Update Process

When a security vulnerability is fixed:

1. **Develop fix:** Create a fix branch with the security patch
2. **Test thoroughly:** Run full test suite and validation gates
3. **Update changelog:** Document the security fix (without exposing the vulnerability)
4. **Release update:** Publish a new version with the fix
5. **Security advisory:** Publish a security advisory if the issue is public
6. **Coordinate disclosure:** If coordinated disclosure is in progress, follow agreed timeline

## Reaching the Maintainer

For security-related questions or vulnerability reports, contact the project maintainer through the repository's issue tracker (for non-sensitive questions) or via private email (for vulnerabilities).

For general security discussions or improvements, please open an issue with the "security" label.
