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
@deffield    updated: 5 Apr. 2018                                                                                                                                                                                                          
'''                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                            
from subprocess import call                                                                                                                                                                                                                 
import json
from simplejson.decoder import JSONDecodeError
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
from ConfigParser import SafeConfigParser
import os

REACT_TO_TOUCH = None
memory = None

class ReactToTouch(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.tts = ALProxy("ALTextToSpeech")
        global memory
        memory = ALProxy("ALMemory")
        memory.subscribeToEvent("TouchChanged",
            "REACT_TO_TOUCH",
            "on_touched")
        
    def set_token(self, token):
        self.token = token
        
    def set_token_greeting(self, greeting):
        self.token_greeting = greeting

    def on_touched(self, strVarName, value):
        if 'Head/Touch' in value[0][0]:
            memory.unsubscribeToEvent("TouchChanged", "REACT_TO_TOUCH")
            self.tts.say(self.token_greeting)
            for letter in self.token.lower():
                self.tts.say(letter)
            memory.subscribeToEvent("TouchChanged", "REACT_TO_TOUCH", "on_touched")

                                                                                                                                                                                                                                            
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
        self.working_directory = '/home/nao/OpenRobertaClient/'
        os.chdir(self.working_directory)
        self.initialize_broker()
        self.DEBUG = True
        self.EASTER_EGG = False
        self.GENERATE_TOKEN = False
        self.SSL_VERIFY = False
        self.token_length = token_length
        self.lab_address = lab_address
        self.firmware_name = 'Nao'
        self.firmware_version = firmware_version
        self.brick_name = self.system.robotName()
        self.robot_name = robot_name
        self.menu_version = '0.0.1'
        self.nao_session = Session()
        self.mac_address = '-'.join(('%012X' % get_mac())[i:i+2] for i in range(0, 12, 2))
        self.token = self.generate_token()
        self.language = self.tts.getLanguage()
        self.last_exit_code = '0'
        self.update_attempts = 36 # 6 minutes of attempts
        self.debug_log_file = open(self.working_directory + 'ora_client.debug', 'w')
        self.initialize_translations()
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
    
    def initialize_broker(self):
        self.myBroker = ALBroker("myBroker", "0.0.0.0", 0, "", 9559)
        self.tts = ALProxy("ALTextToSpeech")
        self.power = ALProxy("ALBattery")
        self.system = ALProxy("ALSystem")
        global REACT_TO_TOUCH
        REACT_TO_TOUCH = ReactToTouch("REACT_TO_TOUCH")
    
    def initialize_translations(self):
        parser = SafeConfigParser()
        parser.read(self.working_directory + 'translations.ini')
        self.TOKEN_SAY = parser.get(self.language, 'TOKEN_SAY')
        global REACT_TO_TOUCH
        REACT_TO_TOUCH.set_token_greeting(self.TOKEN_SAY)
        self.UPDATE_SERVER_DOWN_SAY = parser.get(self.language, 'UPDATE_SERVER_DOWN_SAY')
        self.UPDATE_SERVER_DOWN_HAL_NOT_FOUND_SAY = parser.get(self.language, 'UPDATE_SERVER_DOWN_HAL_NOT_FOUND_SAY')
        self.INITIAL_GREETING = parser.get(self.language, 'INITIAL_GREETING')
        self.TOKEN_GREETING = parser.get(self.language, 'TOKEN_GREETING')
    
    def get_checksum(self, attempts_left):
        if (attempts_left < 1):
            self.log('update server unavailable (cannot get checksum), re-setting number of attempts and continuing further')
            self.tts.say(self.UPDATE_SERVER_DOWN_SAY)
            attempts_left = 36 # 6 minutes more of attempts
        try:
            nao_request = Request('GET', self.lab_address + '/update/nao/' + self.firmware_version + '/hal/checksum')
            nao_prepared_request = nao_request.prepare()
            server_response = self.nao_session.send(nao_prepared_request, verify=self.SSL_VERIFY)
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
            server_response = self.nao_session.send(nao_prepared_request, verify=self.SSL_VERIFY)
            try:
                with open(server_response.headers['Filename'], 'w') as f:
                    f.write(server_response.content)
            except KeyError:
                if hash_value != 'NOHASH':
                    self.log('no update file was found on the server, however server is up, continuing with old hal')
                    return
                else:
                    self.log('no update file was found on the server and no hal present, shutting down client')
                    self.tts.say(self.UPDATE_SERVER_DOWN_HAL_NOT_FOUND_SAY)
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
        global REACT_TO_TOUCH
        if(self.GENERATE_TOKEN):
            token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(self.token_length))
            REACT_TO_TOUCH.set_token(token)
            return token
        else:
            token = ''.join(('%08X' % get_mac())[i:i+2] for i in range(4, 12, 2))
            REACT_TO_TOUCH.set_token(token)
            return token
    
    def get_battery_level(self):
        return self.power.getBatteryCharge()
            
    def send_post(self, command, endpoint):
        nao_request = Request('POST', self.lab_address + endpoint)
        nao_request.data = command
        nao_request.headers['Content-Type'] = 'application/json'
        nao_prepared_request = nao_request.prepare()
        return self.nao_session.send(nao_prepared_request, verify=self.SSL_VERIFY)
    
    def download_and_execute_program(self):
        self.command['cmd'] = self.DOWNLOAD
        self.command['nepoexitvalue'] = '0'
        download_command = json.dumps(self.command)
        server_response = self.send_post(download_command, '/download')
        program_name = self.working_directory + server_response.headers['Filename']
        with open(program_name, 'w') as f:
            f.write(server_response.content)
        self.log('program downloaded, filename: ' + server_response.headers['Filename'])
        self.myBroker.shutdown()
        try:
            self.log('starting user program execution')
            call(['python', program_name])
            self.log('user program execution finished')
            self.last_exit_code = '0'
        except Exception:
            self.last_exit_code = '2'
            self.log('cannot execute user program')
        self.initialize_broker()
    
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
            self.log('Server unavailable, waiting 10 seconds to reconnect.')
            time.sleep(10)
            self.connect()
        self.send_push_request()
    
    def connect(self):
        self.log('Robot token: ' + self.token)
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
        except JSONDecodeError:
            self.log('JSON decoding error (robot was not registered within timeout), reconnecting in 10 seconds...')
            time.sleep(10)
            self.connect()
        
def main():
    rc = RestClient(lab_address='https://test.open-roberta.org/')
    rc.tts.say(rc.INITIAL_GREETING)
    rc.update_firmware()
    rc.tts.say(rc.TOKEN_GREETING)
    rc.connect()
    
if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, KeyError) as e:
        exit(0)
