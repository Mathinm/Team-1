# NFR-6 Usability trial: routine tasks after 30 minutes of training (TC-UX-01)

**Requirement (SRS NFR-6).** A new staff member shall be able to perform routine tasks after
30 minutes of training or less, on a tablet or phone. *Acceptance:* representative new users
complete the defined routine tasks after no more than 30 minutes of training.
**Test case (TC-UX-01 / TC-NFR-09):** 3 people new to the app, 30 minutes of training, then
each logs a batch, records a sale, records a removal, checks a fridge and acknowledges an
alert. Expected: all tasks completed without help.

This file has three parts: (1) the checks already done by script, (2) how to run the trial
with people, (3) the sheets to fill in. The trial itself needs real people: at least 2 (the SRS),
3 to match the test case.

## 1. Checks already done (1 Nov 2026, Chromium, real backend and database)

**Responsive layout.** Every routine-task screen opened at phone size (390 x 844) and tablet size
(820 x 1180):

| Screen | Phone | Tablet |
|---|---|---|
| Login | fits, no sideways scrolling | fits |
| Stock & FEFO, Receive batch form | fits; form in one column | fits |
| Sales | fits | fits |
| Refrigeration | fits; one fridge card per row | fits |
| Alerts (as Manager) | fits; Acknowledge button on every card | fits |
| Products | fits; table turns into cards | fits |

Small tap targets (under 24 px, the WCAG 2.2 minimum): the "I have a one-time code" link on
Login (22 px tall), "Download a sample" on Sales (18 px) and the "Show deactivated" checkbox on
Products (13 px, but its text label can be tapped too). None is needed for the trial tasks;
worth enlarging later.

**Dry run of the tasks on a phone-sized screen** (a script doing what a participant would do):

| Task | Result |
|---|---|
| T1 Log a batch | done: "Batch ... received: 10 kg of Tomato." |
| T2 Record a sale | done: "Sale #... recorded", with the FEFO batches used |
| T3 Record a removal | **cannot be done: there is no removal screen yet** (the backend has `POST /api/removals`, the frontend has no form) |
| T4 Check a fridge | done: Fridge-2 shows 11.5 °C, "Out of range", allowed 0-8 °C |
| T5 Acknowledge an alert | done: the alert moves to Acknowledged |
| T6 Find stock and the first batch to sell | done: Stock & FEFO shows on-hand stock and batches in sell order |

So T3 will fail for every participant until a removal screen exists. Run it anyway and record
it as "not possible", or run the trial after the screen is added.

## 2. Running the trial

**Participants.** 3 (at least 2) people who have never used PMS: friends or classmates outside
the team. Write them down as P1, P2, P3 only, no names. Tell them: "We are testing the app,
not you. Think aloud. You can stop at any time."

**Device.** A phone or tablet on the same Wi-Fi as the laptop running PMS. Find the laptop's
address with `ipconfig` (IPv4 Address, e.g. 192.168.1.20) and open `http://192.168.1.20:3000`
on the device. If it doesn't load, allow port 3000 through Windows Firewall, or use the laptop's
browser in phone view (F12, then the phone icon).

**Prepare the data** (once, before the first participant), in PowerShell in the project folder:
```powershell
docker compose up -d --build
docker compose exec backend python -m app.dev_seed
docker compose exec backend python -m app.device.provision trial-sensors sensor   # copy the key
$env:PMS_DEVICE_KEY="<the key>"
py simulators\sensor_simulator.py --units Fridge-1,Fridge-2,Fridge-3 --count 3 --interval 1
py simulators\sensor_simulator.py --once --unit Fridge-2 --type temperature --value 11.5
```
That gives three fridges, one of them (Fridge-2) too warm with an active TEMPERATURE alert. Before
each new participant, send the 11.5 again for a fresh alert after sending a normal reading
(`--value 4.5`) to close the old one.

**Logins.** Inventory Staff `staff1` / `staff123`, Cashier `cashier1` / `cashier123`, Manager
`manager1` / `manager123`. The Manager needs a 6-digit code (NFR-10): without SMTP it appears
in the backend log, `docker compose logs backend | Select-String "code"`. The facilitator reads
it out; that is part of logging in, not of the task.

**30-minute training** (the facilitator shows, the participant watches and may try; use different
products and numbers from the tasks so the tasks are not just repetition):

| Minutes | Topic | Show |
|---|---|---|
| 0-4 | What PMS is; logging in and out; the menu | Log in as staff1, open the menu, log out |
| 4-11 | Stock & FEFO | Pick a product, read "On hand" and the batch order; receive a batch of Banana |
| 11-16 | Sales (as cashier1) | Record a sale of Milk; read the confirmation and the batches used |
| 16-21 | Refrigeration | Read a fridge card: temperature, allowed range, "Out of range", the chart |
| 21-26 | Alerts (as manager1) | The tabs (Active, Acknowledged, Resolved), what an alert says, Acknowledge |
| 26-30 | Questions | Anything the participant asks |

Stop at 30 minutes. Start the tasks straight after.

**Tasks** (read each one out; don't point at the screen; note the time from "go" to done):

| Task | Log in as | Say | Done when |
|---|---|---|---|
| T1 Log a batch | staff1 | "A delivery came: 10 kg of tomatoes from Fresh Farms, expiring in 4 days. Record it." | Confirmation "Batch ... received" |
| T2 Record a sale | cashier1 | "A customer buys 3 bananas. Record the sale." | Confirmation "Sale #... recorded" |
| T3 Record a removal | staff1 | "2 kg of tomatoes went bad. Record that they were thrown away." | (no screen yet: record "not possible") |
| T4 Check a fridge | staff1 | "Is Fridge-2 at a safe temperature? What is it now?" | Says 11.5 °C and that it is too warm (allowed up to 8 °C) |
| T5 Acknowledge an alert | manager1 | "There is a warning about Fridge-2. Show that you have seen it." | Alert is under Acknowledged |
| T6 Find stock | staff1 | "How much milk is in stock, and which batch should be sold first?" | Says the on-hand amount and the first batch in the list |

**Rules.** Help only if the participant is stuck for 2 minutes or asks; then the task counts as
"with help". A task counts as done "without help" if they finish on their own, even after a wrong
click. Afterwards ask the questions on the sheet.

## 3. Sheets

### Observation sheet (one per participant)

Participant: P__  Date: ______  Device: phone / tablet (model: ______)  Facilitator: ______
Training: started __:__, ended __:__ (must be 30 min or less)

| Task | Done without help? (Y / with help / N / not possible) | Time (min:s) | Wrong clicks / hesitations | Notes (what they said, where they got stuck) |
|---|---|---|---|---|
| T1 Log a batch | | | | |
| T2 Record a sale | | | | |
| T3 Record a removal | | | | |
| T4 Check a fridge | | | | |
| T5 Acknowledge an alert | | | | |
| T6 Find stock | | | | |

After the tasks, ask (1 = very hard, 5 = very easy):
- How easy was the app to use overall? 1 2 3 4 5
- Which task was hardest, and why? ______
- Was anything on the phone/tablet screen too small or hard to tap? ______
- Did 30 minutes of training feel enough? yes / no, because ______

### Results (fill in after the trial)

| Participant | Device | Training (min) | T1 | T2 | T3 | T4 | T5 | T6 | Ease (1-5) |
|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | |
| P2 | | | | | | | | | |
| P3 | | | | | | | | | |

**Verdict.** TC-UX-01 passes when every participant did every available task without help after
at most 30 minutes of training. T3 cannot pass until the removal screen exists: report it as a
known gap. Problems found: ______

**Signed:** facilitator ______  observer ______  date ______
