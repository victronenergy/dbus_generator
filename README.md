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

### Future improvements and additions
- Make it possible configure how to start/stop the genset (relay on BMV, relay on CCGX, relay on ??). Note that this requires work on vedirect-dbus as well, currently it is not possible for the CCGX to control the relay in a BMV.

### Debugging and development on a pc
You will need to run the localsettings dbus service. Get the code from https://github.com/victronenergy/localsettings, and run localsettings.py

Then, in another terminal, run the dummy battery by starting ./test/dummybattery.py.

And then in a last terminal you can run the project: dbus_generator.py
