# Sprint demo videos

| Sprint | File | Length | Issue |
|---|---|---|---|
| Sprint 1 (19–25 Oct) | `sprint1.mp4` | ≤ 1 min | #9 |
| Sprint 2 (26 Oct–1 Nov) | `sprint2.mp4` | ≤ 2 min | #21 |

Keep each file under ~25 MB so GitHub accepts it (record at 720p). If it is
bigger, upload it to YouTube (unlisted) or Google Drive and put the link here.

## How to record (Windows)

1. Start the app: `cd frontend && npm install && npm run dev`, open http://localhost:5173.
   Use the real backend instead of demo data if Sprint 1's backend PRs are merged
   (`VITE_USE_MOCK=false` in `frontend/.env.development`, and `docker compose up` for the API).
2. Press **Win + Alt + R** (Xbox Game Bar) to start/stop recording the browser window,
   or use OBS Studio. Videos land in `Videos\Captures`.
3. Trim to the time limit (Photos app → Edit → Trim), rename and copy here.

## Sprint 1 script (≤ 60 s)

| Time | Show | Say |
|---|---|---|
| 0–8 s | Login page; log in as **cashier1** | "Each role gets its own menu. A cashier only sees Sales." |
| 8–25 s | Sales: sell 15 kg Tomato | "The sale takes stock from the batch that expires first, across two batches, and shows what is left." |
| 25–33 s | Sell Milk more than in stock | "Expired batches are never sold, and an oversized sale is rejected." |
| 33–40 s | Log out, log in as **manager1**, Products | "Managers maintain products: shelf-life, storage temperature, prices and low-stock threshold." |
| 40–55 s | Stock & FEFO: Milk, then Receive batch | "Batches are listed First-Expired-First-Out with time in store and days left. Expired stock is flagged." |
| 55–60 s | Phone-size window (Ctrl+Shift+M in DevTools) | "It works on phones and tablets too." |

## Sprint 2 script (≤ 2 min)

| Time | Show | Say |
|---|---|---|
| 0–20 s | Manager dashboard | "Sales today, stock value, low stock, items expiring in two days, active alerts and waste this week. It refreshes by itself." |
| 20–50 s | Refrigeration → Fridge 2 → **Unit fails**, **Door left open** | "Sensor readings come through the device API. A failure or open door raises an alert straight away." |
| 50–70 s | Alerts → Acknowledge | "Managers acknowledge alerts; we record who and when." |
| 70–100 s | Reports → Wastage, last 30 days → Export PDF and CSV | "Reports cover stock, waste and money lost, sellers, supplier quality, removals, temperature and power events." |
| 100–120 s | Teammates' Sprint 2 features (stock count, removals, markdowns) | Each owner says one line about their feature. |
