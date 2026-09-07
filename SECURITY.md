# Security Policy

Email Automator handles SMTP credentials and recipient information, so security changes should be treated carefully.

## Reporting vulnerabilities

Do not publish credentials, personal data, or exploit details in a public issue. Report security-sensitive problems privately through GitHub and include the affected component, reproduction steps using safe test data, impact, and mitigation ideas.

## Secrets

Never commit SMTP passwords, encryption keys, API tokens, `.env` files, or generated `data/` content. Use environment variables or deployment secret stores.