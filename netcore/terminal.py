"""
This module provides various classes and functions to handle SSH connections
to network devices. It supports direct SSH connections using both Netmiko and
Paramiko, and facilitates device auto-detection and ping functionality.

Classes:
    - NetmikoDirect: Direct SSH connection handler using Netmiko.
    - ParamikoDirect: Direct SSH connection handler using Paramiko.
    - NetmikoTerminal: SSH interaction with network devices, supporting proxies.

Functions:
    - generic_handler: Selects and returns an appropriate connection handler.
    - AutoDetect: Automatically detects the device type for a network device.
    - win_ping: Pings a given IP address and returns the result statistics.
"""

import logging
from copy import copy
from datetime import datetime
from subprocess import Popen, PIPE
from time import sleep

from paramiko import SSHClient, AutoAddPolicy
from netmiko import BaseConnection, redispatch, ConnectHandler
from netmiko.channel import SSHChannel
from netmiko.terminal_server import TerminalServerSSH
from netmiko.ssh_autodetect import SSH_MAPPER_BASE

from .parser import AutoParseTextFSM

from re import search, escape, I, IGNORECASE

# Regular expression pattern to match common command prompts (e.g., $, #, >)
PROMPTS = r'[\$#>]\s?$'

# Regular expression pattern to detect 'assword' (used for password-related prompts)
PASSWORD = r'assword'


def GenericHandler(*args, **kwargs):
    """
    Selects and returns an appropriate connection handler instance based on the
    'handler' keyword argument.

    Supported handlers:
        - 'NETMIKO': Uses NetmikoDirect
        - 'PARAMIKO': Uses ParamikoDirect
        - 'NETMIKO-TERMINAL': Uses NetmikoTerminal

    Args:
        *args: Positional arguments to pass to the handler's constructor.
        **kwargs: Keyword arguments including:
                  - handler (str): Type of handler to initialize.

    Returns:
        object: An instance of the selected handler class.

    Raises:
        ValueError: If the specified handler is not supported or available.
    """
    # Mapping of handler keys to their respective classes
    handlers = {
        'NETMIKO': NetmikoDirect,
        'PARAMIKO': ParamikoDirect,
        'NETMIKO-TERMINAL': NetmikoTerminal
    }

    # Extract the handler type from kwargs or default to 'NETMIKO'
    handler_key = kwargs.pop('handler', 'NETMIKO')
    logging.debug(f"Handler requested: {handler_key}")

    # Attempt to initialize and return the corresponding handler
    if handler_key in handlers:
        logging.debug(f"Initializing handler: {handler_key}")
        return handlers[handler_key](*args, **kwargs)
    else:
        logging.error(f'GenericHandler: "{handler_key}" not available!')
        raise ValueError(f'GenericHandler: "{handler_key}" not available!')


class NetmikoDirect(BaseConnection):
    """
    Handles direct SSH sessions using Netmiko's BaseConnection.

    Supports proxy connections, device auto-detection, output logging,
    and automatic terminal setup.
    """

    def __init__(self, hostname, username, password, proxy=None, logfile=None, device_type='autodetect', *args,
                 **kwargs):
        """
        Initialize a Netmiko connection.

        Args:
            hostname (str): Target hostname or IP.
            username (str): SSH username.
            password (str): SSH password.
            proxy (dict, optional): Proxy connection parameters.
            logfile (str, optional): Log file path.
            device_type (str): Netmiko device type. Default is 'autodetect'.
        """
        self.prompt = ''
        self.device_type = ''
        self.proxy = proxy
        self.logfile = logfile
        logging.debug(f"Initializing NetmikoDirect for {hostname}")
        super().__init__(host=hostname, username=username, password=password, device_type=device_type,
                         session_log=logfile, *args, **kwargs)
        self.setup_channel()

    def establish_connection(self, width: int = 511, height: int = 1000):
        """
        Establish SSH connection, optionally via proxy.

        Args:
            width (int): Terminal width.
            height (int): Terminal height.
        """
        self.create_logger()
        if self.proxy:
            try:
                logging.debug("Establishing proxy connection...")
                ssh_connect_params = self._connect_params_dict()
                self.remote_conn_pre = self._build_ssh_client()
                self.remote_conn_pre.connect(**self.proxy)
                ssh_connect_params['sock'] = self.remote_conn_pre.get_transport().open_channel(
                    'direct-tcpip', (self.host, 22), ('127.0.0.1', 22)
                )
                self.remote_conn_pre.connect(**ssh_connect_params)
                self.remote_conn = self.remote_conn_pre.invoke_shell(width=width, height=height)
                self.channel = SSHChannel(conn=self.remote_conn, encoding=self.encoding)
            except Exception as e:
                logging.error(f"Proxy connection failed: {e}")
                super().establish_connection(width=width, height=height)
        else:
            super().establish_connection(width=width, height=height)

    def set_base_prompt(self, delay_factor=1.0, pattern=r'[$#>]', **kwargs):
        """
        Detect and set device base prompt.

        Returns:
            str: Base prompt.
        """
        prompt = self.find_prompt(delay_factor=delay_factor, pattern=pattern)
        self.base_prompt = prompt if len(prompt) == 1 else prompt[:-1]
        self.prompt = prompt
        return self.base_prompt

    def create_logger(self):
        """
        Write header to session log if available.
        """
        if self.logfile:
            self.session_log.write('{:^79}\n\n'.format('NETMIKO-LOG % ' + datetime.now().strftime("%B %d %H:%M")))

    def setup_channel(self):
        """
        Set up the Netmiko channel with auto device detection, paging off, and terminal size.
        """
        self.device_type = AutoDetect(self)
        self.deviceType = self.device_type
        obj_copy = copy(self)
        redispatch(self, self.device_type)
        self.baseConnectionObject = obj_copy
        self.sendCommand = obj_copy.sendCommand
        self.close = self.disconnect
        self.set_terminal_width()
        self.disable_paging()
        self.secret = self.secret if self.secret else self.password
        self.enable()

    def sendCommand(self, cmd, autoParse=False, key=None):
        """
        Send command to device and optionally parse output.

        Args:
            cmd (str): Command string.
            autoParse (bool): Whether to parse output using TextFSM.
            key (str, optional): Template key.

        Returns:
            str: Raw or parsed command output.
        """
        output = self.send_command(cmd)
        return AutoParseTextFSM(output, cmd, self.deviceType, key).parse() if autoParse else output


class ParamikoDirect(SSHClient):
    """
    Handles direct SSH sessions using Paramiko.

    Provides shell-based command execution with support for proxy and logging.
    """

    def __init__(self, hostname, username, password, proxy=None, logfile=None, secret=None):
        """
        Initialize a Paramiko session.

        Args:
            hostname (str): Target hostname or IP.
            username (str): SSH username.
            password (str): SSH password.
            proxy (dict, optional): Proxy connection parameters.
            logfile (str, optional): Log file path.
            secret (str, optional): Enable secret.
        """
        super().__init__()
        self.hostname = hostname
        self.username = username
        self.password = password
        self.proxy = proxy
        self.prompt = ''
        self.deviceType = ''
        self.secret = secret
        self.logfile = logfile
        self.sock = None
        self.create_logger()
        if proxy:
            self.set_proxy_sock()
        self.set_missing_host_key_policy(AutoAddPolicy)
        self.connect(self.hostname, username=username, password=password, sock=self.sock)
        self.channel = self.invoke_shell()
        self.setup_channel()

    def create_logger(self):
        """
        Create log file and write header if logging is enabled.
        """
        if self.logfile:
            self.logger = open(self.logfile, 'w')
            self.logger.write('{:^79}\n\n'.format('PARAMIKO-LOG % ' + datetime.now().strftime("%B %d %H:%M")))

    def log_output(self, input_str):
        """
        Log command output to the log file.

        Args:
            input_str (str): Output string.
        """
        if self.logfile:
            self.logger.write(input_str.replace('\r\n', '\n'))

    def set_proxy_sock(self):
        """
        Set the proxy socket if proxy is defined.
        """
        try:
            self.set_missing_host_key_policy(AutoAddPolicy())
            self.connect(**self.proxy)
            self.sock = self.get_transport().open_channel('direct-tcpip', (self.hostname, 22), ('127.0.0.1', 22))
        except Exception as e:
            logging.error(f"Proxy setup failed: {e}")

    def setup_channel(self):
        """
        Configure the terminal session (paging off, terminal width).
        """
        self._send_command('terminal length 0')
        self._send_command('terminal width 511')
        self.prompt = self._send_command('').splitlines()[-1].strip()
        self.deviceType = AutoDetect(self)

    def _send_command(self, cmd):
        """
        Internal method to send command and receive output.

        Args:
            cmd (str): Command string.

        Returns:
            str: Command output.
        """
        self.channel.send(f'{cmd}\n'.encode('utf-8'))
        sleep(0.5)
        output = self.channel.recv(65535).decode("utf-8")
        self.log_output(output)
        return output

    def sendCommand(self, cmd, autoParse=False, key=None):
        """
        Send command to device and optionally parse output.

        Args:
            cmd (str): Command string.
            autoParse (bool): Whether to parse output using TextFSM.
            key (str, optional): Template key.

        Returns:
            str: Raw or parsed command output.
        """
        output = self._send_command(cmd)
        return AutoParseTextFSM(output, cmd, self.deviceType, key).parse() if autoParse else output

    def close(self):
        """
        Close channel and SSH session.
        """
        self.channel.close()
        super().close()


class NetmikoTerminal:
    """
    A class for interacting with network devices over SSH using Netmiko.
    Supports both direct device access and proxy (jump host) sessions.

    Attributes:
        hostname (str): Target device hostname or IP.
        username (str): SSH username.
        password (str): SSH password.
        proxy (dict, optional): Proxy connection parameters (hostname, username, password).
        logfile (str, optional): Path to session log file.
        deviceType (str): Network device type (default 'autodetect').
    """

    def __init__(self, hostname, username, password, proxy=None, logfile=None, device_type='autodetect', *args,
                 **kwargs):
        """
        Initialize and connect to the target device using Netmiko.

        Args:
            hostname (str): Hostname or IP of the device.
            username (str): SSH username.
            password (str): SSH password.
            proxy (dict, optional): Proxy host credentials.
            logfile (str, optional): Log file path for Netmiko session log.
            device_type (str): Device type (default is 'autodetect').
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.proxy = proxy
        self.logfile = logfile
        self.deviceType = device_type
        self.args = args
        self.kwargs = kwargs
        self.prompt = ''
        self.errormsg = ''
        self.terminalcode = ''

        logging.debug(f"Initializing NetmikoTerminal for {hostname}")
        self.invokeChannel(*args, **kwargs)
        self.updatePrompt()

    def remoteLogin(self, hostname, username, password):
        """
        Perform remote login through a proxy (terminal server).

        Args:
            hostname (str): Target device hostname.
            username (str): SSH username for target.
            password (str): SSH password for target.
        """
        self._deviceType = self.deviceType
        cmdList = ['ssh']

        if self.kwargs.get('ssh_options'):
            cmdList.extend(self.kwargs['ssh_options'])

        cmdList.extend(['-o', 'StrictHostKeyChecking=no', '-l', username, hostname])
        cmd = ' '.join(cmdList)

        try:
            logging.debug(f"Sending SSH command via proxy: {cmd}")
            self.channel.write_channel(self.channel.normalize_cmd(cmd))
            response = self.channel.read_until_pattern(f'({PASSWORD}|{escape(self.prompt)})')

            if search(PASSWORD, response):
                self.channel.write_channel(self.channel.normalize_cmd(password))
                response = self.channel.read_until_pattern(f'({PROMPTS}|{PASSWORD}|{escape(self.prompt)})')

                if search(PROMPTS, response):
                    self.updatePrompt()
                    self.deviceType = AutoDetect(self)
                    self.prepChannel()
                else:
                    self.errorResponse(response)
            else:
                self.errorResponse(response)
        except Exception as err:
            logging.error(f"Remote login failed: {err}")
            self.errorResponse(str(err))

    def remoteLogout(self, cmd='exit'):
        """
        Log out of the remote session and reset the channel.

        Args:
            cmd (str): Logout command to send (default: 'exit').
        """
        logging.debug("Logging out of remote session.")
        self.channel.write_channel(self.channel.normalize_cmd(cmd))
        self.channel.read_until_pattern(PROMPTS)
        redispatch(self.channel, self._deviceType, session_prep=False)
        self.updatePrompt()

    def close(self):
        """
        Close the current SSH session.
        """
        logging.debug("Closing SSH session.")
        self.channel.disconnect()

    def invokeChannel(self, *args, **kwargs):
        """
        Create an SSH channel to the target device or proxy server.
        """
        if self.proxy:
            logging.debug(f"Connecting via proxy: {self.proxy['hostname']}")
            self.channel = TerminalServerSSH(
                ip=self.proxy['hostname'],
                username=self.proxy['username'],
                password=self.proxy['password'],
                device_type='autodetect',
                session_log=self.logfile,
                *args, **kwargs
            )
            self.updatePrompt()
            self.deviceType = AutoDetect(self)
            self.remoteLogin(hostname=self.hostname, username=self.username, password=self.password)
        else:
            logging.debug(f"Connecting directly to {self.hostname}")
            self.channel = ConnectHandler(
                ip=self.hostname,
                username=self.username,
                password=self.password,
                session_log=self.logfile,
                device_type='autodetect',
                *args, **kwargs
            )
            self.deviceType = AutoDetect(self)

    def updatePrompt(self):
        """
        Update the prompt after login or logout by reading the device prompt.
        """
        self.channel.write_channel(self.channel.RETURN)
        self.prompt = self.channel.read_until_pattern(PROMPTS).splitlines()[-1].strip()
        self.base_prompt = self.prompt[:-1]
        logging.debug(f"Updated prompt: {self.prompt}")

    def errorResponse(self, response):
        """
        Handle SSH login errors and set error messages accordingly.

        Args:
            response (str): SSH response output to analyze.
        """
        logging.error(f"SSH login error response: {response}")
        if search(r'(denied)|([Aa]uth.*[Ff]ail)', response):
            self.terminalcode = 'SSH FAILED'
            self.errormsg = 'Authentication Failed'
        elif search(r'(refused)', response):
            self.terminalcode = 'SSH FAILED'
            self.errormsg = 'Connection Refused'
        elif search(r'(Could not resolve hostname)', response):
            self.terminalcode = 'SSH FAILED'
            self.errormsg = 'HOSTNAME UNRESOLVABLE'
        else:
            self.terminalcode = 'SSH FAILED'
            self.errormsg = 'General Failure'

    def prepChannel(self):
        """
        Prepare the SSH channel for command execution by disabling paging and enabling privileged mode.
        """
        logging.debug("Preparing channel: disabling paging and setting prompt.")
        redispatch(self.channel, self.deviceType, session_prep=False)
        self.channel.set_base_prompt()
        self.channel.set_terminal_width()
        self.channel.disable_paging()
        self.channel.enable()

    def sendCommand(self, cmd, autoParse=False, key=None):
        """
        Send a command to the device and optionally parse the output.

        Args:
            cmd (str): Command string to execute.
            autoParse (bool): Whether to parse the output using TextFSM.
            key (str, optional): Template key for parsing.

        Returns:
            str or list: Raw or parsed command output.
        """
        logging.debug(f"Sending command: {cmd} | AutoParse: {autoParse}")
        output = self.channel.send_command(cmd)
        return AutoParseTextFSM(output, cmd, self.deviceType, key).parse() if autoParse else output


def AutoDetect(channel, disablePagingCmdList=None):
    """
    Automatically detects the device type for a network device connected via Netmiko.

    Sends a list of detection commands defined in SSH_MAPPER_BASE and analyzes
    their responses for known device-specific output patterns.

    Args:
        channel (Netmiko connection object): Active Netmiko connection or proxy shell.
        disablePagingCmdList (list, optional): List of commands to disable terminal paging.

    Returns:
        str: The detected device type string, or an empty string if detection fails.
    """

    # Known invalid response patterns indicating a command is not recognized.
    invalid_responses = [
        r"% Invalid input detected",
        r"syntax error, expecting",
        r"Error: Unrecognized command",
        r"%Error",
        r"command not found",
        r"Syntax Error: unexpected argument",
        r"% Unrecognized command found at",
    ]

    ad_potential_matches = {}
    ad_cache_results = {}

    # Default command to disable paging if not provided
    if disablePagingCmdList is None:
        disablePagingCmdList = ['terminal length 0']

    # Disable paging to get complete command output
    for cmd in disablePagingCmdList:
        logging.debug(f"Sending disable paging command: {cmd}")
        channel.sendCommand(cmd)

    device_type = ''

    # Iterate through known device detection profiles
    for device_type_candidate, detect_data in SSH_MAPPER_BASE:
        cmd = detect_data['cmd']
        search_patterns = detect_data['search_patterns']
        invalid_flag = False
        accuracy = 0

        # Cache output of detection command
        if cmd not in ad_cache_results:
            logging.debug(f"Sending detection command: {cmd}")
            ad_cache_results[cmd] = channel.sendCommand(cmd)

        response = ad_cache_results[cmd]

        # Check if response contains any invalid patterns
        for pattern in invalid_responses:
            if search(pattern, response, flags=IGNORECASE):
                logging.debug(f"Invalid response detected for device {device_type_candidate}: {pattern}")
                invalid_flag = True
                break

        # If no invalid response, check for known device-specific output
        if not invalid_flag:
            for pattern in search_patterns:
                if search(pattern, response, flags=IGNORECASE):
                    accuracy = 99
                    logging.debug(f"Pattern matched for {device_type_candidate}: {pattern}")
                    break

        # Record potential match with accuracy
        if accuracy:
            ad_potential_matches[device_type_candidate] = accuracy
            best_match = sorted(ad_potential_matches.items(), key=lambda t: t[1], reverse=True)

            # Normalize detected device types
            if "cisco_wlc_85" in best_match[0][0]:
                best_match[0] = ("cisco_wlc", 99)
            if "cisco_xr_2" in best_match[0][0]:
                best_match[0] = ("cisco_xr", 99)

            device_type = best_match[0][0]
            logging.debug(f"Detected device type: {device_type}")
            break

    # If no exact match, fallback to best available guess
    if not device_type and ad_potential_matches:
        best_match = sorted(ad_potential_matches.items(), key=lambda t: t[1], reverse=True)
        device_type = best_match[0][0]
        logging.debug(f"Fallback device type used: {device_type}")

    if not device_type:
        logging.error("Device type could not be detected.")

    return device_type


def WinPing(ip, count='1', timeout='500'):
    """
    Pings the given IP address using the Windows ping command and extracts
    connection status, packet statistics, and round-trip times.

    Args:
        ip (str): IP address or hostname to ping.
        count (str, optional): Number of echo requests to send. Defaults to '1'.
        timeout (str, optional): Timeout in milliseconds to wait for each reply. Defaults to '500'.

    Returns:
        dict: A dictionary with the ping results including:
              - Status ('Online' or 'Offline')
              - PacketsSent, PacketsReceived, PacketsLost
              - MinRtt, MaxRtt, AvgRtt
    """
    # Initialize default ping response dictionary
    ping = {
        'Status': '',
        'PacketsSent': '',
        'PacketsReceived': '',
        'PacketsLost': '',
        'MinRtt': '',
        'MaxRtt': '',
        'AvgRtt': ''
    }

    if not ip:
        logging.error("IP address not provided.")
        return ping

    logging.debug(f"Pinging IP: {ip} with count={count}, timeout={timeout}")

    try:
        # Execute Windows ping command
        process = Popen(['ping', '-n', str(int(count)), '-w', str(int(timeout)), ip], stdout=PIPE)
        output, _ = process.communicate()
        output = output.decode('utf-8')

        # Determine if the host is reachable
        if search(r'eply', output, IGNORECASE) and search(r'ttl', output, IGNORECASE):
            ping['Status'] = 'Online'
        else:
            ping['Status'] = 'Offline'

        # Split output into lines for parsing statistics
        for line in output.split('\n'):
            if 'Packets:' in line:
                parts = line.split(',')
                ping['PacketsSent'] = parts[0].split('=')[-1].strip()
                ping['PacketsReceived'] = parts[1].split('=')[-1].strip()
                ping['PacketsLost'] = parts[2].split('=')[-1].strip()
                logging.debug(
                    f"Packet stats: Sent={ping['PacketsSent']}, Received={ping['PacketsReceived']}, Lost={ping['PacketsLost']}")
            elif 'Minimum' in line:
                parts = line.split(',')
                ping['MinRtt'] = parts[0].split('=')[-1].strip()
                ping['MaxRtt'] = parts[1].split('=')[-1].strip()
                ping['AvgRtt'] = parts[2].split('=')[-1].strip()
                logging.debug(f"RTT stats: Min={ping['MinRtt']}, Max={ping['MaxRtt']}, Avg={ping['AvgRtt']}")
    except Exception as e:
        logging.error(f"Ping command failed: {e}")

    return ping
