# NFR-8 FSSAI temperature-recording checklist (TC-COMP-01)

**Requirement (SRS NFR-8).** Temperature control and records shall follow applicable food-safety
guidelines, such as FSSAI requirements. *Acceptance:* a compliance checklist confirms that the
implemented temperature-recording behaviour meets the selected applicable guidance.

**Checked:** branch `s2-10-nfr-checks` (S2-10, #19), 1 November 2026, by Prajwal A.
**Reviewer sign-off:** ______________________ (name, date)

## Guidance selected

| Ref | Guidance | What it asks, in short |
|---|---|---|
| S4-5.1.7 | FSS (Licensing and Registration of Food Businesses) Regulations 2011, Schedule 4 Part II, 5.1.7 | High-risk food received at 5 °C or below |
| S4-5.1.8 | Same, 5.1.8 | Frozen food received at -18 °C or below |
| S4-5.2.2 | Same, 5.2.2 | Cold storage provided where required |
| S4-5.2.5 | Same, 5.2.5 | FIFO / FEFO stock rotation |
| S4-5.3.1.1 | Same, 5.3.1.1 | Systems so that time and temperature are controlled where critical to safety |
| S4-8.1 | Same, 8.1 | Periodic audit of the system against the SOP |
| S4-8.2 | Same, 8.2 | Records of storage (and more) kept for 1 year or the product's shelf life, whichever is more |
| ADV-2026 | FSSAI advisory of 15 Oct 2026 on perishables | Keep prescribed temperatures in storage and transit; keep records and produce them when the authority asks |
| GP | Common cold-chain practice (not an FSSAI clause) | Calibrated sensors; a responsible person reviews the records |

Schedule 4 Part II applies to food businesses in general (a perishables store included). The
clause numbers follow the 2017 FSSAI compendium; check the current text on fssai.gov.in before
relying on them for a real store.

## Checklist

Status: **Met** = PMS does it, with evidence. **Partly** = PMS does it, with a gap noted.
**Not met** = PMS does not do it yet. **Outside PMS** = a store procedure, not software.

| # | Check | Ref | What PMS does (evidence) | Status |
|---|---|---|---|---|
| 1 | Every cold unit is monitored | S4-5.2.2, 5.3.1.1 | Each fridge has a sensor that sends temperature, door and power readings to `POST /api/device/readings`; a unit appears in PMS with its first reading (`test_valid_temperature_reading_is_stored`, `test_units_endpoint_shows_latest_state`) | Met |
| 2 | Monitoring is continuous, not occasional spot checks | S4-5.3.1.1 | Sensors report on a fixed interval (simulator: every 5 s); 100 sensors tested under load (TC-PERF-03). The interval of the real sensors must be set when they are installed (recommend 5 min or less) | Met |
| 3 | Each record shows which unit, the value and the date/time | S4-8.2 | `sensor_readings`: `unit_id`, `value_num` (°C), `recorded_at` (sensor's own time, with time zone), `received_at`, `device_id` | Met |
| 4 | No gaps when the network fails | S4-8.2 | Sensors buffer readings while offline and send them later; they are stored at their original time, in order (`test_30_minute_outage_loses_nothing`, `test_buffered_reading_keeps_original_timestamp`, TC-NFR-07) | Met |
| 5 | Records cannot be changed or deleted through the app; no double counting | S4-8.2 | No API changes or deletes readings or alerts (alerts are never deleted, NFR-7); a resent reading is refused (`test_resent_reading_is_409_and_stored_once`). Database access itself must stay restricted (passwords, NFR-11 encryption, backups) | Met |
| 6 | The allowed temperature range fits the food | S4-5.1.7 | Each fridge has an allowed range, default 0-8 °C, changeable per fridge (`PUT /api/refrigeration/units/{unitId}`, `test_unit_temperature_limits_can_be_changed`). **Gap:** the default 8 °C is above the 5 °C that 5.1.7 uses for high-risk food | Partly |
| 7 | A reading outside the range is noticed at once and staff are told | S4-5.3.1.1 | A reading outside the range raises a critical TEMPERATURE alert and Managers are emailed (`test_temperature_outside_range_alerts_until_back_in_range`); measured 20/20 alerts delivered within 60 s, slowest 18.5 s (TC-PERF-02) | Met |
| 8 | Fridge failure and a door left open are noticed | S4-5.3.1.1 | Power OFF raises UNIT_FAILURE; a door open past its limit (default 5 min, per fridge) raises DOOR_OPEN, even if the sensor goes quiet (`test_unit_failure_changes_status_and_raises_alarm`, `test_door_open_longer_than_limit_raises_alarm`, `test_scheduler_alarms_for_a_door_left_open_when_the_sensor_goes_quiet`) | Met |
| 9 | What was done about a problem is recorded | S4-8.2 | A Manager acknowledges an alert (who and when are stored); the alert closes by itself with the reason and time when the problem ends (`test_recovery_clears_and_logs_the_alarm`); spoiled stock is removed with a reason such as "Temperature breach" (`POST /api/removals`). **Gap:** no field for *what action was taken* | Partly |
| 10 | Records are kept at least 1 year (or the shelf life, if longer) | S4-8.2 | PMS never deletes readings or alerts. Daily backups (NFR-13) are kept 7 days; for safety, keep one backup a month for 12 months on another machine | Met |
| 11 | Records can be produced for an inspector | S4-8.2, ADV-2026 | The Refrigeration screen shows up to 7 days per fridge, with out-of-range readings marked; the readings API returns up to 168 hours. **Gap:** the temperature report and its CSV/PDF export work only in the demo (mock) mode, because the backend has no `/api/reports` yet, so a full period cannot be exported from the real system | Not met |
| 12 | A responsible person reviews the records regularly | S4-8.1, GP | The Refrigeration screen shows each fridge's status and history, but PMS does not record that anyone reviewed them | Not met |
| 13 | Stock is rotated FEFO | S4-5.2.5 | Sales take stock from the batch that expires first; expired batches cannot be sold; the Stock screen lists batches in FEFO order (`tests/test_sales.py`, `tests/test_batches.py`) | Met |
| 14 | The temperature of a delivery is checked when it arrives | S4-5.1.7, 5.1.8 | Receiving a batch records supplier, quantity, time and expiry, but **not** its arrival temperature | Not met |
| 15 | Sensors are accurate (calibration) | GP | Not something software can check: calibrate sensors against a reference thermometer and keep the certificates | Outside PMS |
| 16 | Only the right people see and send temperature data | S4-8.2 | Fridge screens and history: Admin, Manager, Inventory Staff only (`test_refrigeration_access_and_validation`); each sensor sends with its own key, and a POS key cannot send readings | Met |
| 17 | Times are correct and in the store's time | S4-8.2 | Times are stored with their time zone (UTC) and shown in store time (`STORE_TIMEZONE`, default Asia/Kolkata) | Met |

**Result: 11 met, 2 partly met, 3 not met, 1 outside PMS.** The temperature *recording* itself
(items 1-5, 7, 8, 10) meets the selected guidance. The gaps are about limits, follow-up and
getting records out.

## Gaps and suggested follow-ups

| # | Gap | Suggested fix | Owner (suggested) |
|---|---|---|---|
| 6 | Default allowed range goes up to 8 °C | Set `UNIT_TEMP_MAX_C=5` in `.env`, or 5 °C per fridge for those holding dairy, meat or fish (no code change needed) | Store admin / team decision |
| 9 | No "action taken" note | Optional note on `POST /api/alerts/{id}/acknowledge`, shown in the alert history | Backend + frontend |
| 11 | No real export of temperature records | Backend `GET /api/reports/temperature` (the contract already describes it) so the existing CSV/PDF export works with real data | Backend (reports) |
| 12 | No record of review | A daily "checked by" sign-off on the Refrigeration screen, or a paper SOP until then | Team decision |
| 14 | No arrival temperature | Optional "temperature on arrival (°C)" on Receive batch, warning above 5 °C (or above -18 °C for frozen) | Backend + frontend |

## Sources

- Schedule 4 Part II, clauses 5.1.7, 5.1.8, 5.2.2, 5.2.5, 5.3.1.1 (summary of the 2017 compendium): https://www.taxclue.in/blog/schedule-4-part-2-fssai-licensing-regulations-food-operations-and-controls/
- Schedule 4 Part II, clauses 8.1-8.2, record retention: https://www.taxclue.in/blog/schedule-4-part-2-fssai-licensing-regulations-management-testing-audit-and-sanitation/
- FSSAI advisory of 15 Oct 2026 on temperature control for perishables: https://thesouthfirst.com/health/paneer-to-meat-and-fish-fssai-warns-of-seizure-over-temperature-violations/
- FSSAI, sector guidance documents based on Schedule 4: https://fssai.gov.in/faqs/?p=926
