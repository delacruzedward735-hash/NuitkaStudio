# Security Policy

## Supported versions

Security fixes are normally applied to the latest release branch.

| Version | Supported |
|---|---|
| 3.9.x | Yes |
| 3.8.x and older | No |

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose files, execute unintended commands, leak credentials, weaken installer safety, or affect generated build workflows.

Preferred reporting method:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability** to submit a private security advisory.
3. Include the affected version, operating system, reproduction steps, impact, and a minimal proof of concept.

When private vulnerability reporting is not enabled, contact the repository owner privately through the contact method shown on the maintainer's GitHub profile.

The maintainer aims to acknowledge complete reports within seven days. Time to resolution depends on severity, platform access, and the availability of a safe fix.

## Sensitive information

Before sharing logs or screenshots, remove:

- Access tokens and API keys
- Passwords, OTPs, MPINs, and recovery codes
- Private repository URLs
- Personal file paths when they reveal private names
- Signing certificates and private keys
- Payment-account details not intended for public donation use

## Security boundaries

Nuitka Studio launches compilers and packaging tools selected by the user. Only compile projects and run generated workflows from sources you trust. Review advanced arguments, resource mappings, installer scripts, and GitHub Actions changes before execution.
