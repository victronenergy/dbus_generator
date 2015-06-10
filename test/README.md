dbus-generator test
===================

This test can run on CCGX and PC. 
When running on a CCGX the Relay is also tested, on a PC only checks "/State" to know
if the generator is running or not.
As the script runs on timed conditions it takes a while to complete. Total running time 
is arround 150 seconds on a PC and 250 on a CCGX.

Running on a CCGX
--------------------
	./utest.py -v


Running on a PC
---------------
First you need to start localsettings: https://github.com/victronenergy/localsettings
Then run utest.py

	./utest.py -v


