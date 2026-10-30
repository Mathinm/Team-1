# Simulators

POS and sensor simulators for the Device API (SRS FR-17, FR-19; SAD 4.3). Python 3.10+, standard
library only, so there is nothing to install. They run on your machine, not in Docker.

## 1. Get a device key (once per device)

Each device has its own key, shown once. A `pos` key can only send sales, a `sensor` key only
readings.

    docker compose exec backend python -m app.device.provision pos-sim pos
    docker compose exec backend python -m app.device.provision fridge-sensors sensor

(Without Docker: `cd backend && python -m app.device.provision pos-sim pos`.)

## 2. Run

    export PMS_DEVICE_KEY=<key>        # PowerShell: $env:PMS_DEVICE_KEY="<key>"
    python pos_simulator.py            # random sales every 2 s (Ctrl+C to stop)
    python sensor_simulator.py         # temperature/door/power for 3 fridges every 5 s

Options: `--url` (default `http://localhost:8000`, or `PMS_URL`), `--interval`, `--count`,
`--skus` / `--units`, `--key`.

One-off events, handy for test cases:

    python pos_simulator.py --once --sku TOM-01 --quantity 2
    python sensor_simulator.py --once --unit Fridge-2 --type door --value OPEN
    python sensor_simulator.py --once --unit Fridge-1 --type temperature --value abc   # TC-REF-07

## Offline buffering (FR-19, NFR-5)

If the backend is unreachable (or answers 5xx) an event is saved to `pos-buffer.jsonl` /
`sensor-buffer.jsonl` and sent, oldest first, before the next event. Each event has a unique
`eventId`; if a resend had already arrived the backend answers 409 and the simulator treats it as
delivered. Events the backend refuses for good (400/403/404/422, e.g. unknown SKU) are not retried;
they are appended to `*.rejected.jsonl` with the reason. A 401 stops the simulator (wrong key).

To try it: start a simulator, `docker compose stop backend`, wait, `docker compose start backend`.

## Fridge failure and door alarms (FR-15, FR-16)

    python sensor_simulator.py --once --unit Fridge-2 --type power --value OFF     # unit fails
    python sensor_simulator.py --once --unit Fridge-2 --type power --value ON      # recovers
    python sensor_simulator.py --once --unit Fridge-1 --type door --value OPEN --ago 600
        # door "opened 10 minutes ago"; the alarm appears within ~10 s (limit default 5 min)
    python sensor_simulator.py --once --unit Fridge-1 --type door --value CLOSED   # alarm closes
    python sensor_simulator.py --once --unit Fridge-1 --type temperature --value 11.5   # too warm

`--ago S` stamps the reading S seconds in the past, so you do not have to wait for a real timeout.

## Outage test (NFR-5, 30 minutes)

`outage_test.py` stops the backend, keeps a POS and two fridges producing events for N minutes,
starts the backend, synchronises, then proves every event arrived exactly once (each is resent
and must be answered 409) and that stock matches. `docker compose` runs from the project root.

    $env:PMS_POS_KEY="<pos key>"; $env:PMS_SENSOR_KEY="<sensor key>"
    py simulators\outage_test.py --minutes 2 --interval 2     # rehearsal
    py simulators\outage_test.py --minutes 30                 # the NFR-5 test

The buffer file is append-only and crash-safe (a half-written last line is set aside in
`*.corrupt.jsonl`), events always leave in the order they happened, and the queue size is printed
as "waiting to sync".
