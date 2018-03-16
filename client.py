#!/usr/bin/python                                                                                                                                                                                                                           
# encoding: utf-8                                                                                                                                                                                                                           
'''                                                                                                                                                                                                                                         
naoclient.client -- shortdesc                                                                                                                                                                                                               
naoclient.client is an OpenRoberta rest client                                                                                                                                                                                              
It defines nao - server communication                                                                                                                                                                                                       
                                                                                                                                                                                                                                            
@author:     Artem Vinokurov                                                                                                                                                                                                                
@copyright:  2017 Fraunhofer IAIS.                                                                                                                                                                                                          
@license:    GPL 3.0                                                                                                                                                                                                                        
@contact:    artem.vinokurov@iais.fraunhofer.de                                                                                                                                                                                             
@deffield    updated: 14 Mar. 2018                                                                                                                                                                                                          
'''                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                            
from subprocess import call                                                                                                                                                                                                                 
import json                                                                                                                                                                                                                                 
import random                                                                                                                                                                                                                               
import string                                                                                                                                                                                                                               
from requests import Request, Session                                                                                                                                                                                                       
from requests.exceptions import ConnectionError                                                                                                                                                                                             
from uuid import getnode as get_mac                                                                                                                                                                                                         
import datetime                                                                                                                                                                                                                             
import time                                                                                                                                                                                                                                 
import zipfile                                                                                                                                                                                                                              
from naoqi import ALProxy
from naoqi import ALBroker
from naoqi import ALModule
import argparse

# Global variable to store the ReactToTouch module instance
reactToTouch = None
memory = None
TOKEN = ""

class ReactToTouch(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        # No need for IP and port here because
        # we have our Python broker connected to NAOqi broker

        # Create a proxy to ALTextToSpeech for later use
        self.tts = ALProxy("ALTextToSpeech")

        # Subscribe to TouchChanged event:
        global memory
        memory = ALProxy("ALMemory")
        memory.subscribeToEvent("TouchChanged",
            "reactToTouch",
            "onTouched")

    def onTouched(self, strVarName, value):
        if 'Head/Touch' in value[0][0]:
            memory.unsubscribeToEvent("TouchChanged", "reactToTouch")
            for letter in TOKEN.lower():
                self.tts.say(letter)
            memory.subscribeToEvent("TouchChanged", "reactToTouch", "onTouched")

                                                                                                                                                                                                                                            
class RestClient():                                                                                                                                                                                                                         
    '''                                                                                                                                                                                                                                     
    REST endpoints:                                                                                                                                                                                                                         
    /rest/pushcmd (controlling the workflow of the system)                                                                                                                                                                                  
    /rest/download (the user program can be downloaded here)                                                                                                                                                                                
    /rest/update/ (updates for libraries on the robot can be downloaded here)                                                                                                                                                               
    /update/nao/v2-1-4-3/hal - GET new hal
    /update/nao/v2-1-4-3/hal/checksum - GET hal checksum
    '''
    
    REGISTER = 'register'
    PUSH = 'push'
    REPEAT = 'repeat'
    ABORT = 'abort'
    UPDATE = 'update'
    DOWNLOAD = 'download'
    CONFIGURATION = 'configuration' #not yet used
    
    def __init__(self, token_length=8, lab_address='https://lab.open-roberta.org/', 
                 firmware_version='v2-1-4-3', robot_name='nao'):
        self.initializeNAO()
        self.DEBUG = True
        self.EASTER_EGG = False
        self.GENERATE_TOKEN = False
        self.parameterString = "\\RSPD=100\\ "
        self.token_length = token_length
        self.lab_address = lab_address
        self.firmware_name = 'Nao'
        self.firmware_version = firmware_version
        self.brick_name = robot_name
        self.robot_name = robot_name
        self.menu_version = '0.0.1'
        self.nao_session = Session()
        self.mac_address = '-'.join(('%012X' % get_mac())[i:i+2] for i in range(0, 12, 2))
        self.token_from_mac = ''.join(('%08X' % get_mac())[i:i+2] for i in range(4, 12, 2))
        self.token = self.generate_token()
        global TOKEN
        if(self.GENERATE_TOKEN):
            TOKEN = self.token
        else:
            TOKEN = self.token_from_mac
        self.last_exit_code = '0'
        self.update_attempts = 36 # 6 minutes of attempts
        self.working_directory = '/home/nao/OpenRobertaClient/'
        self.debug_log_file = open(self.working_directory + 'ora_client.debug', 'w')
        self.command = {
                            'firmwarename': self.firmware_name,
                            'robot': self.robot_name,
                            'macaddr': self.mac_address,
                            'cmd': self.REGISTER,
                            'firmwareversion': self.firmware_version,
                            'token': self.token,
                            'brickname': self.brick_name,
                            'battery': self.get_battery_level(),
                            'menuversion': self.menu_version,
                            'nepoexitvalue': self.last_exit_code
                        }        
    
    def initializeNAO(self):
        self.myBroker = ALBroker("myBroker", "0.0.0.0",  # Listen to anyone
                                 0,  # find a free port and use it
                                 "",  # parent broker ip
                                 9559)  # parent broker port
        self.tts = ALProxy("ALTextToSpeech")
        self.memory = ALProxy("ALMemory")
        self.mark = ALProxy("ALLandMarkDetection")
        global reactToTouch
        reactToTouch = ReactToTouch("reactToTouch")
    
    def get_checksum(self, attempts_left):
        if (attempts_left < 1):
            self.log('update server unavailable (cannot get checksum), shutting down open roberta client')
            self.tts.say('OpenRoberta server unavailable, client is shutting down. Check my connection to OpenRoberta and restart the client by rebooting me, or restarting from console.')
            exit(0)
        try:
            nao_request = Request('GET', self.lab_address + '/update/nao/' + self.firmware_version + '/hal/checksum')
            nao_prepared_request = nao_request.prepare()
            server_response = self.nao_session.send(nao_prepared_request)
            return server_response.content
        except ConnectionError:
            self.log('update server unavailable, sleeping for 10 seconds before next attempt')
            time.sleep(10)
            return self.get_checksum(attempts_left - 1)

    def update_firmware(self):
        checksum = self.get_checksum(self.update_attempts)
        hash_file_name = self.working_directory + 'firmware.hash'
        try:
            f = open(hash_file_name, 'r')
        except IOError:
            f = open(hash_file_name, 'w')
            f.write('NOHASH')
        f = open(hash_file_name, 'r')
        hash_value = f.readline()
        if hash_value != checksum:
            self.log('updating hal library')
            nao_request = Request('GET', self.lab_address + '/update/nao/' + self.firmware_version + '/hal')
            nao_prepared_request = nao_request.prepare()
            server_response = self.nao_session.send(nao_prepared_request)
            try:
                with open(server_response.headers['Filename'], 'w') as f:
                    f.write(server_response.content)
            except KeyError:
                if hash_value != 'NOHASH':
                    self.log('no update file was found on the server, however server is up, continuing with old hal')
                    return
                else:
                    self.log('no update file was found on the server and no hal present, shutting down client')
                    self.tts.say('Sorry, hal update error occurred and no hal present, have to quit for now. Try again later.')
                    exit(0)
            zip_ref = zipfile.ZipFile(server_response.headers['Filename'], 'r')
            zip_ref.extractall(self.working_directory)
            zip_ref.close()
            f = open(hash_file_name, 'w')
            f.write(checksum)
            self.log('hal library updated, checksum written: ' + checksum)
        else:
            self.log('hal library up to date')
        
    def log(self, message):
        if self.DEBUG:
            print '[DEBUG] - ' + str(datetime.datetime.now()) + ' - ' + message
            self.debug_log_file.write('[DEBUG] - ' + str(datetime.datetime.now()) + ' - ' + message + '\n')
    
    def generate_token(self):
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(self.token_length))
    
    def get_battery_level(self):
        return '8.4'
            
    def send_post(self, command, endpoint):
        nao_request = Request('POST', self.lab_address + endpoint)
        nao_request.data = command
        nao_request.headers['Content-Type'] = 'application/json'
        nao_prepared_request = nao_request.prepare()
        return self.nao_session.send(nao_prepared_request)
    
    def download_and_execute_program(self):
        self.command['cmd'] = self.DOWNLOAD
        self.command['nepoexitvalue'] = '0'
        download_command = json.dumps(self.command)
        server_response = self.send_post(download_command, '/download')
        program_name = server_response.headers['Filename']
        with open(program_name, 'w') as f:
            f.write(server_response.content)
        self.log('program downloaded, filename: ' + program_name)
        self.myBroker.shutdown()
        try:
            call(['python', program_name])
            self.last_exit_code = '0'
        except Exception:
            self.last_exit_code = '2'
            self.log('cannot execute program')
        self.initializeNAO()
    
    def send_push_request(self):
        self.log('started polling at ' + str(datetime.datetime.now()))
        self.command['cmd'] = self.PUSH
        self.command['nepoexitvalue'] = self.last_exit_code
        push_command = json.dumps(self.command)
        try:
            server_response = self.send_post(push_command, '/pushcmd')
            if server_response.json()['cmd'] == 'repeat':
                self.log('received response at ' + str(datetime.datetime.now()))
            elif server_response.json()['cmd'] == 'download':
                self.log('download issued')
                self.download_and_execute_program()
            elif server_response.json()['cmd'] == 'abort':
                pass
            else:
                pass
        except ConnectionError:
            self.log('Server unavailable')
            time.sleep(10)
            self.connect()
        self.send_push_request()
    
    
    def connect(self):
        self.tts.say("My token is ")
        if (self.GENERATE_TOKEN):
            print 'Robot token: ' + self.token
            for letter in self.token:
                self.tts.say(self.parameterString + letter + '\\RST\\')
        else:
            print('Robot token: ' + self.token_from_mac)
            for letter in self.token_from_mac.lower():
                self.tts.say(self.parameterString + letter + '\\RST\\')
            self.command['token'] = self.token_from_mac
        if(self.EASTER_EGG):
            f = open('quotes', 'r')
            quotes = f.readlines()
            quote = quotes[random.randint(0, len(quotes)-1)]
            self.tts.say(quote)
        self.command['cmd'] = self.REGISTER
        register_command = json.dumps(self.command)
        try:
            server_response = self.send_post(register_command, '/pushcmd')
            if server_response.json()['cmd'] == 'repeat':
                self.send_push_request()
            elif server_response.json()['cmd'] == 'abort':
                pass
            else:
                pass
        except ConnectionError:
            self.log('Server unavailable, reconnecting in 10 seconds...')
            time.sleep(10)
            self.connect()
        
def main():
    rc = RestClient(lab_address='http://10.116.20.62:1999')
    rc.update_firmware()
    rc.connect()
    
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        exit(0)

