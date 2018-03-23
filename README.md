This repository holds a client for NAO robot to connect to OpenRoberta lab.

Currently the only way to load this client is by using SSH or SFTP client.

1. Login to NAO
2. Create a folder under /home/nao, for example OpenRobertaClient
3. Download client.py and translations.ini to the aforementioned folder.
4. Edit /home/nao/naoqi/preferences/autoload.ini and put a path to client.py (inclusive client.py) under the last section (program)

Step 4 is needed for client auto-start, if this is not the desired mode of operation, omit this step and launch the client manualy each time needed.

Currently NAO pronounces the token for establishing the connection on client start and whenever the head is touched (precisely head middle), although this functionality is not available during user program runtime to free head touch events for user programs. This behaviour will be changed soon, so NAO will say the token _only_ when the head is touched and not automatically. There will be some indication that the client started though.
