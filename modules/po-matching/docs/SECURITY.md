# Security & Compliance — 3-Way PO Matching

**Backbone AI Ltd — Internal & Client Documentation**
**Version**: 1.0.0 | **March 2026**

---

## 1. Compliance Frameworks

This module is designed and operated in alignment with:

| Framework | Status | Notes |
|---|---|---|
| **UK GDPR** | Compliant | Data residency in UK, DPA template provided |
| **Cyber Essentials** | Aligned | All 5 technical controls met |
| **ISO 27001** | Aligned | Formal certification in roadmap (Q4 2026) |
| **PCI DSS** | N/A | No cardholder data processed |
| **HMRC MTD** | Aware | Invoice data can feed MTD-compliant pipelines |

---

## 2. Data Residency

All data is stored and processed exclusively within **AWS eu-west-2 (London)**.

- No data transits outside the UK
- No sub-processors outside the UK EEA
- AI extraction calls to Anthropic API: data is not used for model training (Anthropic commercial agreement)
- Client instructed processing agreement (CIPA) provided as standard

---

## 3. Encryption

### At Rest
- **Documents (PDFs)**: AES-256-GCM, encrypted before S3 upload
- **Database fields**: Standard PostgreSQL encryption at rest (RDS encryption enabled)
- **Sensitive config** (API keys, IMAP credentials): AES-256-GCM encrypted in database, key stored in AWS Secrets Manager
- **Encryption keys**: Per-client keys, rotated annually, stored in AWS KMS (eu-west-2)

### In Transit
- All HTTP traffic: TLS 1.3 minimum (TLS 1.2 disallowed)
- IMAP connections: TLS mandatory, STARTTLS accepted only if IMAP server enforces
- Internal service-to-service: TLS with mutual authentication
- ERP API connections: TLS 1.2 minimum (some legacy ERPs do not support 1.3)

---

## 4. Authentication & Authorisation

### User Authentication (Portal)
- JWT tokens: HS256, 15-minute access token lifetime
- Refresh tokens: 30-day lifetime, single-use (rotated on each refresh)
- MFA: TOTP (Google Authenticator / Authy) — optional in v1.0, mandatory in v1.1
- Session invalidation: logout invalidates refresh token immediately
- Brute-force protection: 5 failed attempts → 15-minute lockout

### ERP & System Connections (Persistent — No Repeated Auth Prompts)

ERP connections are authenticated **once at setup time** and remain permanently connected. The system handles all token management silently in the background — no user or operator is ever prompted to re-authenticate during normal operation.

**How this works per system:**

| System | Auth Method | Persistence Mechanism |
|---|---|---|
| Sage 200 Cloud | OAuth 2.0 | Refresh token stored encrypted. Auto-refreshed 5 minutes before expiry. Never expires unless manually revoked. |
| Xero | OAuth 2.0 | Same — refresh token rotated silently. 60-day offline access tokens. |
| SAP Business One | Service Layer session | Session token auto-renewed every 25 minutes (SAP default 30-minute timeout). |
| Email (IMAP) | App password / OAuth | Credentials stored encrypted. Single persistent IMAP IDLE connection maintained. Reconnects automatically on drop. |
| On-premise Sage 200 | SQL Server service account | Read-only SQL service account. Credentials stored in KMS. Connection pooled and always-on. |

**Key principle**: Backbone AI owns and manages all service credentials. The client never sees or interacts with connection credentials. If a token expires or a connection drops, the system recovers silently and alerts the Backbone AI ops team — not the client.

### API Authentication (Machine-to-Machine)
- API keys: 256-bit random, stored as bcrypt hash
- Keys are scoped (read-only, write, admin)
- Key rotation: self-service via portal, old key valid for 24 hours post-rotation

---

## 5. Audit Trail

Every action in the system is written to an immutable append-only audit log:

- Document received
- AI extraction started / completed
- Matching run started / completed
- Match result created
- Match approved / rejected / overridden
- Configuration changed
- User login / logout
- ERP sync completed
- Any error or exception

Audit log properties:
- **Immutable**: records cannot be updated or deleted (Postgres trigger enforces)
- **Timestamped**: UTC timestamp to microsecond precision
- **Actor recorded**: system, user ID, or API key reference
- **IP recorded**: hashed (SHA-256 + salt) — identifiable to Backbone AI, pseudonymised by default
- **Retention**: 7 years (HMRC requirement for financial records)
- **Export**: available to client as JSON or CSV on request

---

## 6. Access Control

### Principle of Least Privilege
- Each user role has the minimum permissions required for their function
- No shared accounts
- Service accounts have read-only ERP access only
- No direct database access granted to application users

### Network Controls
- Application servers in private subnet (no direct internet access)
- Database accessible only from application subnet
- All inbound traffic via ALB (port 443 only)
- Outbound: allowlist of ERP API endpoints, Anthropic API, AWS services
- SSH access: via AWS Systems Manager Session Manager only (no open SSH port)

### WAF Rules (Cloudflare)
- OWASP Core Rule Set enabled
- Rate limiting: 100 requests/minute per IP (portal), 1000/minute (API with valid key)
- Bot protection: challenge on suspicious patterns
- SQL injection and XSS patterns blocked at edge

---

## 7. Vulnerability Management

- **Dependencies**: automated scanning via Dependabot (GitHub) + manual review monthly
- **SAST**: Bandit (Python) on every commit
- **Container scanning**: Trivy on every Docker image build
- **Penetration testing**: annual third-party pen test (planned Q3 2026)
- **CVE response**: critical CVEs patched within 24 hours, high within 7 days

---

## 8. Incident Response

| Severity | Definition | Response Time | Notification |
|---|---|---|---|
| P1 — Critical | Data breach, system down | 1 hour | CEO + DPO immediately |
| P2 — High | Matching failures, ERP disconnected | 4 hours | Ops team + account manager |
| P3 — Medium | Delayed processing, elevated errors | 24 hours | Ops team |
| P4 — Low | Minor anomalies | Next business day | Internal log |

**Data breach procedure:**
1. Contain: isolate affected systems
2. Assess: determine scope and data affected
3. Notify ICO within 72 hours (UK GDPR Article 33)
4. Notify affected clients immediately
5. Root cause analysis within 5 business days

---

## 9. UK GDPR Compliance

### Data Processed
| Data Category | Legal Basis | Retention |
|---|---|---|
| Invoice PDFs | Legitimate interest (financial record-keeping) | 7 years (HMRC) |
| Supplier contact data | Legitimate interest | Duration of supplier relationship |
| User account data | Contract | Duration of employment + 90 days |
| Audit logs | Legitimate interest (fraud prevention, compliance) | 7 years |
| IP addresses (hashed) | Legitimate interest (security) | 12 months |

### Data Subject Rights
All rights under UK GDPR are supported:
- **Right of access**: client can export all their data via portal
- **Right to erasure**: supported for user account data; invoice/audit data retained for HMRC compliance with legal hold applied
- **Right to portability**: JSON export available on request
- **Right to object**: handled via Backbone AI DPO

### Sub-processors
| Sub-processor | Location | Purpose | Safeguard |
|---|---|---|---|
| AWS (Amazon) | UK (eu-west-2) | Cloud infrastructure | UK GDPR Article 28 DPA |
| Anthropic | USA | AI document extraction | SCCs + data processing agreement (no training on data) |
| Cloudflare | UK edge | CDN + WAF | UK GDPR Article 28 DPA |

---

## 10. Business Continuity

- **RTO** (Recovery Time Objective): 4 hours
- **RPO** (Recovery Point Objective): 15 minutes (RDS automated backups every 15 minutes)
- **Database backups**: daily snapshots retained 35 days, transaction logs continuous
- **Document backups**: S3 versioning enabled, cross-region replication to eu-west-1 (Ireland)
- **Failover**: RDS Multi-AZ — automatic failover in < 60 seconds
- **DR test**: quarterly failover drill

---

*Backbone AI Ltd — Confidential*
*Security version 1.0.0 — March 2026*
*Review date: September 2026*
