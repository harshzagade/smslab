# Security Policy

SMSLab is a mock-only development and test harness. It must never send messages to a carrier or contact an external provider.

## Reporting a vulnerability

Report suspected safety or security defects privately to the repository owner through GitHub's security reporting feature.

## Project safety invariants

- No network transport or third-party messaging SDK is included.
- Non-mock transport configurations are rejected.
- Recipients must be in the validated test-recipient allowlist.
- Request volume and concurrency have hard maximums.
- OTP values are not placed in reports or logs; the OTP service stores only a digest.
- The test suite scans package imports for common networking modules.

Do not use this project to send real messages or to test systems you do not own or have permission to assess.
