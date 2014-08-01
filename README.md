dbus_generator
==============

Python script taking care of generator start/stop based on battery status. To be used on the Color Control GX.

Current implementation is meant for DC Generators, where a BMV battery monitor is used to monitor its current, and it expects to start and stop this genset by opening and closing the relay on the CCGX.

### Project status
Work in progress, current functionality not yet finished. 

### Future improvements and additions
- It should also work for AC gensets, connected to AC input 1 or 2 from the Multi. To get ideas on the necessary conditions, see the options in VEConfigure3-virtual switch tab, the options in the Generator start/stop assistant in VEConfigure3. And then add other possibilities that we have because there is a clock in the CCGX. For example silent nights, auto starting before the night or auto starting every x days to allow equalisation.
- Make it possible configure how to start/stop the genset (relay on BMV, relay on CCGX, relay on ??). Note that this requires work on vedirect-dbus as well, currently it is not possible for the CCGX to control the relay in a BMV.
- Publish ourselves on the dbus as a generator (com.victronenergy.dcgenerator and com.victronenergy.acgenerator). See also outcommented code in dbus_generator.py

### Debugging and development on a pc
You will need to the run the localsettings dbus service. Get the code from https://github.com/victronenergy/localsettings, and run localsettings.py

Then, in another terminal, run the dummy battery by starting ./test/dummybattery.py.

And then in a last terminal you can run the project: dbus_generator.py

