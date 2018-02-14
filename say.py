#!/usr/bin/python

from naoqi import ALProxy
import sys

tts = ALProxy("ALTextToSpeech", "0.0.0.0", 9559)
parameterString = "\\RSPD=60\\ "
tts.say("Current token is " + parameterString + sys.argv[1] + "\\RST\\") 
