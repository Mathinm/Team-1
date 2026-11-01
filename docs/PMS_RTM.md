# Requirements Traceability Matrix (RTM)

**Project:** Perishables Management System (PMS)  
**Document Version:** 1.0  
**Date:** November 1, 2026  
**Status:** Approved & Verified  
**Standard References:** SRS v1.0 (`PMS_SRS.docx`), SAD v1.1 (`PMS_SAD.docx`), Test Case Document v1.1 (`PMS_Test_Cases_v1-1.pdf`)  
**Requirement Identifier:** NFR-15 / TC-RTM-01  

---

## 1. Executive Summary & Traceability Protocol

The Requirements Traceability Matrix (RTM) establishes bidirectional traceability between system requirements, architecture design areas, project work items (GitHub Issues and Pull Requests), test case specifications, and automated test implementation files.

### Status Legend
- **P (Passed):** Requirement fully implemented and verified via automated test suites.
- **A (Accepted):** Requirement verified through architectural review, inspection, configuration check, or operational trial.
- **N (Not Yet Verified):** Requirement open or awaiting verification.

---

## 2. Functional Requirements Traceability Matrix (FR-1 to FR-19)

| Req ID (SRS) | STP Ref (Test Doc) | Module / Area | Description | Issue Link | PR Link | Test Case(s) | Automated Test File & Implementation | Status |
|---|---|---|---|---|---|---|---|---|
| **FR-1** | FR-33 | Product Master Data | Add, edit, and deactivate products with standard fields (shelf life, temperature range, prices, threshold) | [#5](https://github.com/Mathinm/Team-1/issues/5) | [#24](https://github.com/Mathinm/Team-1/pull/24), [#27](https://github.com/Mathinm/Team-1/pull/27) | TC-PROD-01, TC-MD-01..05 | `backend/tests/test_products.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-2** | FR-4 | Stock Tracking & Sales | Record received batches with item, category, supplier, quantity, units, received time, and expiry date | [#6](https://github.com/Mathinm/Team-1/issues/6) | [#28](https://github.com/Mathinm/Team-1/pull/28) | TC-STK-01, TC-STK-01..03 | `backend/tests/test_batches.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-3** | FR-5 | Stock Tracking & Sales | Deduct stock automatically on POS sale in strict FEFO (First-Expired, First-Out) order | [#7](https://github.com/Mathinm/Team-1/issues/7) | [#25](https://github.com/Mathinm/Team-1/pull/25) | TC-STK-02, TC-STK-04..06 | `backend/tests/test_sales.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-4** | FR-6 | Stock Tracking & Sales | Restock recorded batches to increment on-hand inventory quantity | [#6](https://github.com/Mathinm/Team-1/issues/6) | [#28](https://github.com/Mathinm/Team-1/pull/28) | TC-STK-03, TC-STK-07 | `backend/tests/test_batches.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-5** | FR-8 | Stock Tracking & Sales | Calculate and display batch age (time in store) and remaining shelf life before expiry | [#6](https://github.com/Mathinm/Team-1/issues/6) | [#28](https://github.com/Mathinm/Team-1/pull/28) | TC-STK-04, TC-STK-08 | `backend/tests/test_batches.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-6** | FR-9 | Stock Tracking & Sales | Suggest FEFO selling order with batches sorted ascending by expiry date | [#6](https://github.com/Mathinm/Team-1/issues/6) | [#28](https://github.com/Mathinm/Team-1/pull/28) | TC-STK-05, TC-STK-09 | `backend/tests/test_batches.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-7** | FR-36 | Stock Tracking & Sales | Block sale of expired batches at POS billing (422 EXPIRED_BATCH) | [#7](https://github.com/Mathinm/Team-1/issues/7) | [#25](https://github.com/Mathinm/Team-1/pull/25) | TC-STK-06, TC-STK-10..11 | `backend/tests/test_sales.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-8** | FR-37 | Stock Tracking & Sales | Support manual single-sale entries and bulk CSV sales file imports | [#7](https://github.com/Mathinm/Team-1/issues/7) | [#25](https://github.com/Mathinm/Team-1/pull/25) | TC-STK-07, TC-STK-12..14 | `backend/tests/test_sales.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-9** | FR-38 | Stock Tracking & Sales | Physical stock count; show variance from system stock; record adjustments with reason and worker | [#10](https://github.com/Mathinm/Team-1/issues/10) | [#34](https://github.com/Mathinm/Team-1/pull/34) | TC-STK-08, TC-STK-15..16 | `backend/tests/test_stock.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **FR-10** | FR-10 | Low-Stock Alerts | Advance low-stock alert projected 1 day before stock depletes using 7-day rolling average | [#13](https://github.com/Mathinm/Team-1/issues/13) | [#36](https://github.com/Mathinm/Team-1/pull/36) | TC-ALT-01, TC-LOW-01..03 | `backend/tests/test_alerts.py`<br>`frontend/src/api/mock/alerts.test.js` | **P** |
| **FR-11** | FR-11 | Low-Stock Alerts | Immediate low-stock alert triggered when on-hand inventory drops strictly below configured threshold | [#13](https://github.com/Mathinm/Team-1/issues/13) | [#36](https://github.com/Mathinm/Team-1/pull/36) | TC-ALT-02, TC-LOW-04..05 | `backend/tests/test_alerts.py`<br>`frontend/src/api/mock/alerts.test.js` | **P** |
| **FR-12** | FR-13 | Expiry, Removal & Markdown | Expiry notifications sent 1 day before expiry and on expiration day; integrated with scheduler | [#11](https://github.com/Mathinm/Team-1/issues/11) | [#37](https://github.com/Mathinm/Team-1/pull/37) | TC-EXP-01, TC-EXP-01..02 | `backend/tests/test_notifications.py` | **P** |
| **FR-13** | FR-15 | Expiry, Removal & Markdown | Record non-expiry stock losses (spoilage, damage, temperature breach) with reason and worker | [#10](https://github.com/Mathinm/Team-1/issues/10) | [#34](https://github.com/Mathinm/Team-1/pull/34) | TC-EXP-02, TC-EXP-03..05 | `backend/tests/test_stock.py` | **P** |
| **FR-14** | FR-42 | Expiry, Removal & Markdown | Rule-based markdowns capped at MAX_MARKDOWN_PERCENT with automated scheduler run and sell-through tracking | [#12](https://github.com/Mathinm/Team-1/issues/12) | [#40](https://github.com/Mathinm/Team-1/pull/40) | TC-EXP-03, TC-EXP-06..08 | `backend/tests/test_markdowns.py` | **P** |
| **FR-15** | FR-17 | Refrigeration / Sensing | Monitor refrigeration unit operational state and trigger UNIT_FAILURE alarm on power loss | [#14](https://github.com/Mathinm/Team-1/issues/14) | [#36](https://github.com/Mathinm/Team-1/pull/36) | TC-SEN-01, TC-REF-01..02 | `backend/tests/test_refrigeration.py`<br>`frontend/src/api/mock/alerts.test.js` | **P** |
| **FR-16** | FR-23 | Refrigeration / Sensing | Trigger DOOR_OPEN alarm when a refrigeration unit door remains open past configured limit | [#14](https://github.com/Mathinm/Team-1/issues/14) | [#36](https://github.com/Mathinm/Team-1/pull/36) | TC-SEN-02, TC-REF-03..04 | `backend/tests/test_refrigeration.py`<br>`frontend/src/api/mock/alerts.test.js` | **P** |
| **FR-17** | FR-43 | Device API & Simulators | Authenticated device API with device keys and eventId idempotency for temperature, door, power | [#4](https://github.com/Mathinm/Team-1/issues/4) | [#25](https://github.com/Mathinm/Team-1/pull/25) | TC-SEN-03, TC-REF-05..07 | `backend/tests/test_device.py` | **P** |
| **FR-18** | FR-29 | Reporting & Dashboard | Real-time dashboard and exportable CSV/PDF reports (waste, sales, sellers, suppliers, temp history) | [#16](https://github.com/Mathinm/Team-1/issues/16), [#17](https://github.com/Mathinm/Team-1/issues/17) | [#38](https://github.com/Mathinm/Team-1/pull/38), [#39](https://github.com/Mathinm/Team-1/pull/39) | TC-REP-01, TC-REP-01..05 | `frontend/src/api/mock/reports.test.js`<br>`frontend/src/pages/DashboardPage.jsx` | **P** |
| **FR-19** | FR-30 | Offline Buffering & Sync | Offline event buffering during network outage and de-duplicated synchronization upon reconnection | [#15](https://github.com/Mathinm/Team-1/issues/15) | [#36](https://github.com/Mathinm/Team-1/pull/36) | TC-REP-02, TC-REP-06..07 | `backend/tests/test_offline_sync.py` | **P** |

---

## 3. Security Requirements Traceability Matrix (SEC-1 to SEC-5)

| Req ID (SRS) | STP Ref (Test Doc) | Module / Area | Description | Issue Link | PR Link | Test Case(s) | Automated Test File & Implementation | Status |
|---|---|---|---|---|---|---|---|---|
| **SEC-1** | FR-1 | Security / Authentication | Unique user ID and password authentication; generic invalid credentials message | [#3](https://github.com/Mathinm/Team-1/issues/3) | [#26](https://github.com/Mathinm/Team-1/pull/26) | TC-AUTH-01, TC-AUTH-01..03 | `backend/tests/test_auth.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **SEC-2** | FR-2 | Security / RBAC | Role-Based Access Control enforcing permissions across Admin, Manager, Inventory Staff, Cashier | [#3](https://github.com/Mathinm/Team-1/issues/3) | [#26](https://github.com/Mathinm/Team-1/pull/26) | TC-AUTH-02, TC-AUTH-04..06 | `backend/tests/test_access.py`<br>`frontend/src/api/mock/handlers.test.js` | **P** |
| **SEC-3** | FR-3 | Security / Lockout & Session | Account lockout (HTTP 423) after 5 consecutive failed logins; idle session termination | [#18](https://github.com/Mathinm/Team-1/issues/18) | [#35](https://github.com/Mathinm/Team-1/pull/35) | TC-AUTH-03, TC-AUTH-07..09 | `backend/tests/test_lockout.py` | **P** |
| **SEC-4** | FR-31 | Security / User Admin | Admin user administration: create, update, deactivate accounts and assign roles | [#3](https://github.com/Mathinm/Team-1/issues/3) | [#26](https://github.com/Mathinm/Team-1/pull/26) | TC-AUTH-04, TC-AUTH-10..12 | `backend/tests/test_users.py` | **P** |
| **SEC-5** | FR-32 | Security / Password Reset | Secure email password reset token flow (SHA-256 hashed, 30-min expiry, single-use) | [#18](https://github.com/Mathinm/Team-1/issues/18) | [#35](https://github.com/Mathinm/Team-1/pull/35) | TC-AUTH-05, TC-AUTH-13..14 | `backend/tests/test_reset.py` | **P** |

---

## 4. Non-Functional Requirements Traceability Matrix (NFR-1 to NFR-15)

| Req ID (SRS) | STP Ref (Test Doc) | Quality Attribute | Target SLA / Specification | Issue Link | PR Link | Test Case(s) | Verification Evidence / Test Suite | Status |
|---|---|---|---|---|---|---|---|---|
| **NFR-1** | NFR-1 | Performance | Stock updates visible across screens within 5 s (95% target); single queries < 3 s | [#19](https://github.com/Mathinm/Team-1/issues/19) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-PERF-01, TC-NFR-01 | `perf/stock_latency.py`<br>`backend/tests/test_sales.py` | **P** |
| **NFR-2** | NFR-3 | Performance | Alerts delivered to designated recipients within 60 s | [#13](https://github.com/Mathinm/Team-1/issues/13), [#19](https://github.com/Mathinm/Team-1/issues/19) | [#36](https://github.com/Mathinm/Team-1/pull/36), [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-PERF-02, TC-NFR-03 | `perf/alert_latency.py`<br>`backend/tests/test_alerts.py` | **P** |
| **NFR-3** | NFR-5 | Scalability | Concurrency: supports 50 users, 5,000 batches, 100 sensors under load | [#19](https://github.com/Mathinm/Team-1/issues/19) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-PERF-03, TC-NFR-04 | `perf/locustfile.py`<br>`backend/app/load_seed.py` | **P** |
| **NFR-4** | NFR-8 | Availability | 99.5% monthly availability; Docker restart policy `unless-stopped`; health checks | [#19](https://github.com/Mathinm/Team-1/issues/19), [#31](https://github.com/Mathinm/Team-1/issues/31) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-REL-01, TC-NFR-06 | `docker-compose.yml`<br>`backend/tests/test_health.py` | **P** |
| **NFR-5** | NFR-9 | Reliability | Zero data loss during 30-minute network outage; local buffer with de-duplicated sync | [#15](https://github.com/Mathinm/Team-1/issues/15), [#19](https://github.com/Mathinm/Team-1/issues/19) | [#36](https://github.com/Mathinm/Team-1/pull/36), [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-REL-02, TC-NFR-07 | `backend/tests/test_offline_sync.py`<br>`simulators/outage_test.py` | **P** |
| **NFR-6** | NFR-10 | Usability | Staff able to perform routine operations with <= 30 min training; intuitive UI | [#19](https://github.com/Mathinm/Team-1/issues/19) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-UX-01, TC-NFR-09 | `docs/NFR-6-usability-trial.md`<br>`frontend/src/lib/validation.test.js` | **A** |
| **NFR-7** | NFR-11 | Data Retention | Retention of temperature logs, stock movements, and audit records for at least 2 years | [#19](https://github.com/Mathinm/Team-1/issues/19) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-DATA-01, TC-NFR-10 | Database indexes & timestamp partitioning schema design | **A** |
| **NFR-8** | NFR-12 | Compliance | Food safety compliance (FSSAI) for cold-chain refrigeration audit logs (0-8°C) | [#14](https://github.com/Mathinm/Team-1/issues/14), [#19](https://github.com/Mathinm/Team-1/issues/19) | [#36](https://github.com/Mathinm/Team-1/pull/36), [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-COMP-01, TC-NFR-11 | `docs/NFR-8-fssai-checklist.md`<br>`backend/tests/test_refrigeration.py` | **P** |
| **NFR-9** | NFR-14 | Security | Passwords stored as salted cryptographic hashes (Argon2id implementation) | [#3](https://github.com/Mathinm/Team-1/issues/3), [#18](https://github.com/Mathinm/Team-1/issues/18) | [#26](https://github.com/Mathinm/Team-1/pull/26), [#35](https://github.com/Mathinm/Team-1/pull/35) | TC-SEC-06, TC-NFR-12 | `backend/tests/test_passwords.py` | **P** |
| **NFR-10** | NFR-15 | Security | Two-factor authentication (2FA) enforced for Manager and Admin roles via email OTP | [#18](https://github.com/Mathinm/Team-1/issues/18) | [#35](https://github.com/Mathinm/Team-1/pull/35) | TC-SEC-07, TC-NFR-13 | `backend/tests/test_2fa.py` | **P** |
| **NFR-11** | NFR-17 | Security | Sensitive employee data encrypted at rest (Fernet/AES-128-CBC) with Manager/Admin access | [#18](https://github.com/Mathinm/Team-1/issues/18) | [#35](https://github.com/Mathinm/Team-1/pull/35) | TC-SEC-08, TC-NFR-14 | `backend/tests/test_employee_data.py` | **P** |
| **NFR-12** | NFR-20 | Performance | Removal alert delivered within 2 minutes of recording stock loss | [#11](https://github.com/Mathinm/Team-1/issues/11) | [#37](https://github.com/Mathinm/Team-1/pull/37) | TC-PERF-04, TC-NFR-05 | `backend/tests/test_notifications.py` | **P** |
| **NFR-13** | NFR-21 | Recovery | Automated daily pg_dump backup with verified restore script in CI drill | [#19](https://github.com/Mathinm/Team-1/issues/19) | [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-REL-03, TC-NFR-08 | `ops/pms-backup.sh`<br>`.github/workflows/ci.yml` | **P** |
| **NFR-14** | NFR-25 | Scalability | Store ID foreign key partition on all store data tables for multi-tenant scalability | [#5](https://github.com/Mathinm/Team-1/issues/5), [#19](https://github.com/Mathinm/Team-1/issues/19) | [#24](https://github.com/Mathinm/Team-1/pull/24), [#41](https://github.com/Mathinm/Team-1/pull/41) | TC-SCAL-01, TC-NFR-15 | `backend/app/models.py`<br>`backend/tests/test_products.py` | **P** |
| **NFR-15** | NFR-26 | Traceability | Every FR traces to an automated test case; RTM updated and verified via TC-RTM-01 | [#20](https://github.com/Mathinm/Team-1/issues/20) | Current PR | TC-RTM-01, TC-NFR-16 | `backend/tests/test_rtm.py`<br>`docs/PMS_RTM.md` | **P** |

---

## 5. Bidirectional Cross-Reference Mapping (SRS v1.0 ↔ Test Case Document v1.1)

To reconcile the difference in requirement numbering identified in SAD Section 4.6, the table below provides a complete cross-reference between SRS v1.0 and Test Case Document v1.1:

| SRS v1.0 Req ID | Test Case Doc v1.1 Req ID | Requirement Area | Primary Test Case IDs |
|---|---|---|---|
| **FR-1** | FR-33 | Product Master Data | TC-PROD-01, TC-MD-01..05 |
| **FR-2** | FR-4 | Batch Receipt | TC-STK-01, TC-STK-01..03 |
| **FR-3** | FR-5 | POS Sale FEFO Deduction | TC-STK-02, TC-STK-04..06 |
| **FR-4** | FR-6 | Restock Recording | TC-STK-03, TC-STK-07 |
| **FR-5** | FR-8 | Batch Age & Shelf Life | TC-STK-04, TC-STK-08 |
| **FR-6** | FR-9 | FEFO Suggestion | TC-STK-05, TC-STK-09 |
| **FR-7** | FR-36 | Block Expired Sale | TC-STK-06, TC-STK-10..11 |
| **FR-8** | FR-37 | Manual & CSV Sales | TC-STK-07, TC-STK-12..14 |
| **FR-9** | FR-38 | Stock Count & Adjustment | TC-STK-08, TC-STK-15..16 |
| **FR-10** | FR-10 | Projected Low Stock | TC-ALT-01, TC-LOW-01..03 |
| **FR-11** | FR-11 | Immediate Low Stock | TC-ALT-02, TC-LOW-04..05 |
| **FR-12** | FR-13 | Expiry Notifications | TC-EXP-01, TC-EXP-01..02 |
| **FR-13** | FR-15 | Stock Loss / Removals | TC-EXP-02, TC-EXP-03..05 |
| **FR-14** | FR-42 | Rule-Based Markdowns | TC-EXP-03, TC-EXP-06..08 |
| **FR-15** | FR-17 | Fridge Unit Failure | TC-SEN-01, TC-REF-01..02 |
| **FR-16** | FR-23 | Fridge Door Open Alarm | TC-SEN-02, TC-REF-03..04 |
| **FR-17** | FR-43 | Sensor Device API | TC-SEN-03, TC-REF-05..07 |
| **FR-18** | FR-29 | Dashboard & Reports | TC-REP-01, TC-REP-01..05 |
| **FR-19** | FR-30 | Offline Buffering & Sync | TC-REP-02, TC-REP-06..07 |
| **SEC-1** | FR-1 | Authentication | TC-AUTH-01, TC-AUTH-01..03 |
| **SEC-2** | FR-2 | RBAC Permissions | TC-AUTH-02, TC-AUTH-04..06 |
| **SEC-3** | FR-3 | Account Lockout & Idle | TC-AUTH-03, TC-AUTH-07..09 |
| **SEC-4** | FR-31 | Admin User Management | TC-AUTH-04, TC-AUTH-10..12 |
| **SEC-5** | FR-32 | Password Reset | TC-AUTH-05, TC-AUTH-13..14 |
| **NFR-1** | NFR-1 | Stock Latency | TC-PERF-01, TC-NFR-01 |
| **NFR-2** | NFR-3 | Alert Delivery Latency | TC-PERF-02, TC-NFR-03 |
| **NFR-3** | NFR-5 | Concurrency | TC-PERF-03, TC-NFR-04 |
| **NFR-4** | NFR-8 | Availability & Recovery | TC-REL-01, TC-NFR-06 |
| **NFR-5** | NFR-9 | Outage Sync Reliability | TC-REL-02, TC-NFR-07 |
| **NFR-6** | NFR-10 | Usability & Training | TC-UX-01, TC-NFR-09 |
| **NFR-7** | NFR-11 | Data Retention | TC-DATA-01, TC-NFR-10 |
| **NFR-8** | NFR-12 | Food Safety Compliance | TC-COMP-01, TC-NFR-11 |
| **NFR-9** | NFR-14 | Password Salted Hashes | TC-SEC-06, TC-NFR-12 |
| **NFR-10** | NFR-15 | Two-Factor Auth (2FA) | TC-SEC-07, TC-NFR-13 |
| **NFR-11** | NFR-17 | Employee Data Encryption | TC-SEC-08, TC-NFR-14 |
| **NFR-12** | NFR-20 | Removal Alert Delivery | TC-PERF-04, TC-NFR-05 |
| **NFR-13** | NFR-21 | Daily Backup & Restore | TC-REL-03, TC-NFR-08 |
| **NFR-14** | NFR-25 | Multi-Tenant Store ID | TC-SCAL-01, TC-NFR-15 |
| **NFR-15** | NFR-26 | RTM Traceability | TC-RTM-01, TC-NFR-16 |

---

## 6. Summary Traceability Metrics

- **Total Functional Requirements (FRs):** 19 / 19 Traceable (100% Coverage)
- **Total Security Requirements (SECs):** 5 / 5 Traceable (100% Coverage)
- **Total Non-Functional Requirements (NFRs):** 15 / 15 Traceable (100% Coverage)
- **Total Requirements Traced:** 39 / 39 (100%)
- **Automated Backend Test Cases:** 333 tests passing across 21 test suites (`backend/tests/`)
- **Automated Frontend Test Cases:** 45 tests passing across 6 test suites (`frontend/src/`)
- **Verification Result:** All 19 Functional Requirements and 5 Security Requirements verified with status **Passed (P)**. All 15 Non-Functional Requirements verified with status **Passed (P)** or **Accepted (A)**. Zero unverified requirements remain.
