__version__ = "0.0.2"

__copyright__ = "Copyright 2017-2019, Fraunhofer IAIS"
__author__ = 'Artem Vinokurov'
__email__ = 'artem.vinokurov@iais.fraunhofer.de'

'''
naoclient.client -- shortdesc
naoclient.client is an OpenRoberta rest client
It defines nao - server communication

@author:     Artem Vinokurov
@copyright:  2017-2019 Fraunhofer IAIS.
@license:    GPL 3.0
@contact:    artem.vinokurov@iais.fraunhofer.de
@deffield    updated: 23 May 2019
'''

import stk.runner
import stk.events
import stk.services
import stk.logging

from subprocess import call, Popen
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
import sys


REACT_TO_TOUCH = None
ProgramManager = None
memory = None


class ProgramManagerModule(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)

    def set_running_program_process(self, program_process):
        self.program_process = program_process

    def subscribe_event(self):
        try:
            global memory
            memory.subscribeToEvent("TouchChanged",
                                    "ProgramManager",
                                    "on_touched")
        except Exception as e:
            print str(e)

    def unsubscribe_event(self):
        try:
            global memory
            memory.unsubscribeToEvent("TouchChanged", "ProgramManager")
        except Exception as e:
            print str(e)

    def __collect_touched_sensors(self, sensors):
        touched_bodies = []
        for s in sensors:
            if s[1]:
                touched_bodies.append(s[0])
        return touched_bodies

    def __kill_program(self):
        print("Killing process with pid %s " %
              self.program_process.pid)
        self.program_process.kill()

    def on_touched(self, strVarName, values):
        """This will be called each time when there is touch."""
        try:
            self.unsubscribe_event()
            touched_bodies = self.__collect_touched_sensors(values)
            if len(touched_bodies) > 2:
                self.__kill_program()
        except Exception as e:
            print str(e)
        finally:
            self.subscribe_event()


class ReactToTouch(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.tts = ALProxy("ALTextToSpeech")
        self.subscribe_event()

    def set_token(self, token):
        self.token = token

    def set_token_greeting(self, greeting):
        self.token_greeting = greeting

    def unsubscribe_event(self):
        try:
            self.tts.stopAll()
            global memory
            memory.unsubscribeToEvent("TouchChanged", "REACT_TO_TOUCH")
        except Exception as e:
            print e

    def subscribe_event(self):
        try:
            global memory
            memory.subscribeToEvent(
                "TouchChanged", "REACT_TO_TOUCH", "on_touched")
        except Exception as e:
            print e

    def on_touched(self, strVarName, values):
        """This will be called each time when there is touch."""
        try:
            self.unsubscribe_event()
            for value in values:
                if 'Head/Touch' in value[0] and value[1] == True:
                    self.tts.say(self.token_greeting)
                    for letter in self.token.lower():
                        self.tts.say(letter)
                    break
        except Exception as e:
            print e
        finally:
            self.subscribe_event()


class RestClient():
    '''
    REST endpoints:
    /rest/pushcmd (controlling the workflow of the system)
    /rest/download (the user program can be downloaded here)
    /rest/update/ (updates for libraries on the robot can be downloaded here)
    /update/nao/2-8/hal - GET new hal
    /update/nao/2-8/hal/checksum - GET hal checksum
    '''
    REGISTER = 'register'
    PUSH = 'push'
    REPEAT = 'repeat'
    ABORT = 'abort'
    UPDATE = 'update'
    DOWNLOAD = 'download'
    CONFIGURATION = 'configuration'  # not yet used

    def __init__(self, token_length=8, lab_address='https://lab.open-roberta.org',
                 firmware_version='2-8', robot_name='nao'):
        self.working_directory = sys.path[0] + '/'
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
        self.menu_version = __version__
        self.nao_session = Session()
        self.mac_address = '-'.join(('%012X' %
                                     get_mac())[i:i+2] for i in range(0, 12, 2))
        self.token = self.generate_token()
        self.language = self.tts.getLanguage()
        self.last_exit_code = '0'
        self.update_attempts = 36  # 6 minutes of attempts
        self.debug_log_file = open(
            self.working_directory + 'ora_client.debug', 'w')
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
        global memory
        memory = ALProxy("ALMemory")
        self.tts = ALProxy("ALTextToSpeech")
        self.power = ALProxy("ALBattery")
        self.system = ALProxy("ALSystem")
        global REACT_TO_TOUCH
        REACT_TO_TOUCH = ReactToTouch("REACT_TO_TOUCH")
        global ProgramManager
        ProgramManager = ProgramManagerModule('ProgramManager')

    def reinitialize_say_lines(self):
        global REACT_TO_TOUCH
        REACT_TO_TOUCH.set_token_greeting(self.TOKEN_SAY)
        REACT_TO_TOUCH.set_token(self.token)

    def initialize_translations(self):
        parser = SafeConfigParser()
        parser.read(self.working_directory + 'translations.ini')
        self.TOKEN_SAY = parser.get(self.language, 'TOKEN_SAY')
        global REACT_TO_TOUCH
        REACT_TO_TOUCH.set_token_greeting(self.TOKEN_SAY)
        self.UPDATE_SERVER_DOWN_SAY = parser.get(
            self.language, 'UPDATE_SERVER_DOWN_SAY')
        self.UPDATE_SERVER_DOWN_HAL_NOT_FOUND_SAY = parser.get(
            self.language, 'UPDATE_SERVER_DOWN_HAL_NOT_FOUND_SAY')
        self.INITIAL_GREETING = parser.get(self.language, 'INITIAL_GREETING')
        self.TOKEN_GREETING = parser.get(self.language, 'TOKEN_GREETING')

    def get_checksum(self, attempts_left):
        if (attempts_left < 1):
            self.log(
                'update server unavailable (cannot get checksum), re-setting number of attempts and continuing further')
            self.tts.say(self.UPDATE_SERVER_DOWN_SAY)
            attempts_left = 36  # 6 minutes more of attempts
        try:
            nao_request = Request(
                'GET', self.lab_address + '/update/nao/' + self.firmware_version + '/hal/checksum')
            nao_prepared_request = nao_request.prepare()
            server_response = self.nao_session.send(
                nao_prepared_request, verify=self.SSL_VERIFY)
            return server_response.content
        except ConnectionError:
            self.log(
                'update server unavailable, sleeping for 10 seconds before next attempt')
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
            nao_request = Request(
                'GET', self.lab_address + '/update/nao/' + self.firmware_version + '/hal')
            nao_prepared_request = nao_request.prepare()
            server_response = self.nao_session.send(
                nao_prepared_request, verify=self.SSL_VERIFY)
            try:
                with open(server_response.headers['Filename'], 'w') as f:
                    f.write(server_response.content)
            except KeyError:
                if hash_value != 'NOHASH':
                    self.log(
                        'no update file was found on the server, however server is up, continuing with old hal')
                    return
                else:
                    self.log(
                        'no update file was found on the server and no hal present, shutting down client')
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
            self.debug_log_file.write(
                '[DEBUG] - ' + str(datetime.datetime.now()) + ' - ' + message + '\n')

    def generate_token(self):
        global REACT_TO_TOUCH
        if(self.GENERATE_TOKEN):
            token = ''.join(random.choice(string.ascii_uppercase + string.digits)
                            for _ in range(self.token_length))
            REACT_TO_TOUCH.set_token(token)
            return token
        else:
            token = ''.join(('%012X' % get_mac())[
                i:i+2] for i in range(4, 12, 2))
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
        program_name = self.working_directory + \
            server_response.headers['Filename']
        with open(program_name, 'w') as f:
            f.write(server_response.content)
        self.log('program downloaded, filename: ' +
                 server_response.headers['Filename'])
        # self.myBroker.shutdown()
        global REACT_TO_TOUCH
        REACT_TO_TOUCH.unsubscribe_event()
        global ProgramManager
        ProgramManager.subscribe_event()

        try:
            self.log('starting user program execution')
            prog_proc = Popen(['python', program_name])
            ProgramManager.set_running_program_process(prog_proc)
            prog_proc.communicate()
            self.log('user program execution finished')
            self.last_exit_code = '0'
        except Exception as e:
            print e
            self.last_exit_code = '2'
            self.log('cannot execute user program')

        REACT_TO_TOUCH.subscribe_event()
        ProgramManager.unsubscribe_event()
        # self.initialize_broker()
        # self.reinitialize_say_lines()

    def send_push_request(self):
        self.log('started polling at ' + str(datetime.datetime.now()))
        self.command['cmd'] = self.PUSH
        self.command['nepoexitvalue'] = self.last_exit_code
        push_command = json.dumps(self.command)
        try:
            server_response = self.send_post(push_command, '/pushcmd')
            if server_response.json()['cmd'] == 'repeat':
                self.log('received response at ' +
                         str(datetime.datetime.now()))
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
            self.log(
                'JSON decoding error (robot was not registered within timeout), reconnecting in 10 seconds...')
            time.sleep(10)
            self.connect()


class OpenRobertaClient(object):
    APP_ID = "de.fhg.iais.roberta.OpenRobertaClient"

    def __init__(self, qiapp):
        self.qiapp = qiapp
        self.session = qiapp.session
        self.events = stk.events.EventHelper(qiapp.session)
        self.s = stk.services.ServiceCache(qiapp.session)
        self.logger = stk.logging.get_logger(qiapp.session, self.APP_ID)

    def _wait_for_service(self, service_name, max_delay_in_seconds=60):
        for i in range(max_delay_in_seconds):
            try:
                service = self.session.service(service_name)
                return True
            except RuntimeError:
                time.sleep(1.0)
                return
        # Failed, give up

    def on_start(self):
        self._wait_for_service("ALTextToSpeech")
        self._wait_for_service("ALBattery")
        self._wait_for_service("ALSystem")
        # unregister REACT_TO_TOUCH if it's already running (it shouldn't be)
        if self.s.REACT_TO_TOUCH:
            self.s.REACT_TO_TOUCH.stop()
        if self.s.ProgramManager:
            self.s.ProgramManager.stop()
        rc = RestClient()
        rc.tts.say(rc.INITIAL_GREETING)
        rc.update_firmware()
        rc.tts.say(rc.TOKEN_GREETING)
        rc.connect()
        self.logger.info("Application started.")

    def stop(self):
        self.qiapp.stop()

    def on_stop(self):
        self.logger.info("Application finished.")
        self.events.clear()


if __name__ == "__main__":
    stk.runner.run_service(OpenRobertaClient)
