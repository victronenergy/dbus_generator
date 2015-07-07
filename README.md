dbus_generator
==============

Python script taking care of generator start/stop based on battery status and/or AC load. To be used on the Color Control GX.

The CCGX internal relay can be used to start a generator using its internal relay. With this script you can set conditions to make the relay open or close.

Available conditions: 
- Manual
- State of charge (SOC)
- AC load
- Battery current
- Battery voltage
- Maintenance


For more details of how it works and all available options, check the manual: http://www.victronenergy.com/live/ccgx:generator_start_stop

### Future improvements and additions
- Make it possible configure how to start/stop the genset (relay on BMV, relay on CCGX, relay on ??). Note that this requires work on vedirect-dbus as well, currently it is not possible for the CCGX to control the relay in a BMV.

### Debugging and development on a pc
You will need to run the localsettings dbus service. Get the code from https://github.com/victronenergy/localsettings, and run localsettings.py

Then, in another terminal, run the dummy battery by starting ./test/dummybattery.py.

And then in a last terminal you can run the project: dbus_generator.py

