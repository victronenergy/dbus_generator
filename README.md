dbus_generator
==============

[![Build Status](https://travis-ci.org/victronenergy/dbus_generator.svg?branch=master)](https://travis-ci.org/victronenergy/dbus_generator)

Python script taking care of generator start/stop based on battery status and/or AC load. To be used on a GX device.
With this script you can set conditions to start or stop the generator.

Currently the script supports the following configurations
- Controlling a generator using Relay0 on a GX device; the `com.victronenergy.generator.startstop0/Generator0` path is used
- Controlling a Fischer Panda generator that is connected through CAN-bus; the `com.victronenergy.generator.startstop0/FischerPanda0` is used

Available conditions: 
- Manual
- State of charge (SOC)
- AC load
- Battery current
- Battery voltage
- Maintenance
- Inverter high temperature warning
- Inverter overload warning

For more details of how it works and all available options, check the manual: http://www.victronenergy.com/live/ccgx:generator_start_stop

### Digital Input Inhibit

A `com.victronenergy.digitalinput.*` service configured with `/Type=12` is treated as a genset inhibit input. Discovery and removal are driven entirely by `device_added` and `device_removed` callbacks.

**Operational model:**
1. When a digital input service with `/Type=12` appears, inhibit tracking begins and the capability is persisted
2. `/State=12` means the generator may run; `/State=13` means the generator is inhibited
3. When the service disappears or its type changes away from `12`, the service is removed and re-added by `dbus-digitalinputs` — `device_removed` fires and Error #5 is set until a replacement is found via `device_added`
4. Writing `0` to `/DigitalInput/InhibitSet` clears inhibit tracking entirely

`/DigitalInput/InhibitActive` reflects the current inhibit state: `None` when no type-12 input is being followed, `0` when the followed input is at `/State=12` (run allowed), and `1` when the followed input is at `/State=13` (inhibited).

**Error semantics:**
- **Error #4 — Digital input inhibit disabled**: A type-12 input is being followed and its `/State` is `13` (inhibited)
- **Error #5 — Digital input not found**: A type-12 input was previously seen but is not currently available

The "previously seen" state is persisted in `/Settings/Generator{N}/DigitalInputInhibitSeen`. On restart, if this setting is `1` but no type-12 digital input service is present, Error #5 is set immediately to prevent the generator starting.

### Future improvements and additions
- Make it possible configure how to start/stop the genset (relay on BMV, relay on CCGX, relay on ??). Note that this requires work on vedirect-dbus as well, currently it is not possible for the CCGX to control the relay in a BMV.

### Debugging and development on a pc
You will need to run the localsettings dbus service. Get the code from https://github.com/victronenergy/localsettings, and run localsettings.py

Then, in another terminal, run the dummy battery by starting ./test/dummybattery.py.

And then in a last terminal you can run the project: dbus_generator.py
