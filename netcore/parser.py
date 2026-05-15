"""
This module contains classes and functions for parsing raw device output using TextFSM templates.

The primary focus of the module is to provide functionality for parsing raw command outputs from network devices.
It supports parsing with both local templates (if available) and NTC templates using the TextFSM library.

Classes:
    LogParser: A class for parsing raw device output, segregating it into hostname and command outputs, and parsing those outputs using TextFSM templates.
    ConfigParser: A class for parsing configuration-style output (e.g., "show running-config") into structured data.
    AutoParseTextFSM: A class for parsing raw string data using TextFSM templates. It provides the ability to parse command outputs using local or NTC templates.

Functions:
    None directly, as the primary functionality is provided by the classes in this module.

Usage:
    - `LogParser` is used to process raw device output, extract command outputs, and parse them with TextFSM templates.
    - `ConfigParser` is used to parse configuration-like data, such as "show running-config" outputs, into a structured list of dictionaries.
    - `AutoParseTextFSM` is a specialized class for parsing raw command output based on TextFSM templates, with support for both local and NTC template directories.

This module leverages TextFSM for parsing structured command output from network devices and can be extended for various network device types. It also includes error handling with logging for failed parsing attempts.
"""

import re
import json
import os
import importlib.resources as packages
from textfsm.clitable import CliTable, CliTableError
import logging


class LogParser:
    """
    A class to parse raw device output and segregate it into hostname and
    show command outputs, and then parse those outputs using TextFSM templates.

    Attributes:
        rawString (str): Raw device output as a string.
        library (str): Library used for parsing. Default is 'TEXTFSM'.
        deviceType (str): Type of the device (e.g., 'cisco_ios').
        data (dict): Dictionary holding parsed and raw data.

    Methods:
        segregate(rawString): Segregates the raw output into hostname and command outputs.
        useTextFSM(): Uses the TextFSM library to parse the device outputs.
    """

    def __init__(self, rawString, deviceType=None, parserModule='TEXTFSM'):
        """
        Initializes LogParser with raw string, device type, and parsing library.

        Args:
            rawString (str): Raw device output as a string.
            deviceType (str, optional): Type of device for template selection.
            library (str, optional): Parsing library (default is 'TEXTFSM').
        """
        self.rawString = rawString
        self.parserModule = parserModule
        self.deviceType = deviceType
        self.data = {}
        self.segregate(rawString)
        if parserModule == 'TEXTFSM':
            self.useTextFSM()

    def segregate(self, rawString):
        """
        Segregates the raw device output into hostname and command outputs.

        Args:
            rawString (str): The raw output string from the device.

        Updates:
            self.data['hostname']: Device hostname.
            self.data['outputs']: Dictionary of show commands and their outputs.
        """
        basepromptREG = re.search(r'\n(\S+)\s*([>#])', rawString)
        showcommandREG = r'(\S+)\s*([>#])\s*(show.*)'

        self.data['hostname'] = ''
        self.data['outputs'] = {}

        if basepromptREG:
            self.data['hostname'] = basepromptREG.group(1)

            cmd = ''
            startFLAG = None
            for line in rawString.splitlines():
                searchOBJ = re.search(showcommandREG, line, re.IGNORECASE)
                if searchOBJ:
                    cmd = searchOBJ.group(3).strip()
                    self.data['outputs'][cmd] = {}
                    self.data['outputs'][cmd]['raw'] = ''
                    startFLAG = True
                    continue
                if startFLAG:
                    if searchOBJ or re.search(r'(\S+)([>#])', line):
                        startFLAG = False
                if startFLAG:
                    self.data['outputs'][cmd]['raw'] += line + '\n'

    def useTextFSM(self):
        """
        Parses the raw output using TextFSM templates and stores the parsed data.

        Uses TextFSM's CliTable to parse each command's output. If parsing fails,
        the error is stored in the output.
        """
        if not self.deviceType:
            self.deviceType = 'cisco_ios'

        try:
            packagepath = packages.files(package='ntc_templates')
            ntcTemplateDir = str(packagepath.parent.joinpath('ntc_templates', 'templates'))
            indexFile = os.path.join(ntcTemplateDir, "index")
            cliTableOBJ = CliTable(indexFile, ntcTemplateDir)

            for cmd, cmdData in self.data['outputs'].items():
                self.data['outputs'][cmd]['parsed'] = []
                if re.search('show run', cmd):
                    # Use ConfigParser for show run command
                    parser = ConfigParser(cmdData['raw'])
                    self.data['outputs'][cmd]['parsed'] = parser.config
                    continue
                try:
                    cliTableOBJ.ParseCmd(cmdData['raw'], {"Command": cmd, "Platform": self.deviceType})
                    data = []
                    for row in cliTableOBJ:
                        rowData = {}
                        for index, element in enumerate(row):
                            rowData[cliTableOBJ.header[index].lower()] = element
                        data.append(rowData)
                    self.data['outputs'][cmd]['parsed'] = data
                except Exception as error:
                    logging.error(f"Failed to parse command '{cmd}': {error}")
                    self.data['outputs'][cmd]['parsed'] = str(error)
        except Exception as error:
            logging.error(f"Error in useTextFSM: {error}")
            raise


class ConfigParser:
    """
    A class to parse configuration-style outputs (e.g., 'show running-config')
    into structured data.

    Attributes:
        raw (str): Raw configuration data as a string.
        config (list): Parsed configuration data as a list of dictionaries.

    Methods:
        parse(raw): Parses the raw configuration data.
        getIndent(posx, lines): Returns the indentation level of a line.
        getBody(posx, lines): Returns the body of a block of lines with consistent indentation.
        query(regex, lines): Recursively searches for lines matching the regex.
    """

    def __init__(self, raw):
        """
        Initializes ConfigParser with raw configuration data.

        Args:
            raw (str): The raw configuration data to parse.
        """
        self.raw = raw
        self.config = self.parse(raw)

    def parse(self, raw):
        """
        Parses the raw configuration data into a list of dictionaries.

        Args:
            raw (str): The raw configuration data.

        Returns:
            list: A list of parsed configuration data.
        """
        lines = raw.splitlines()
        config = []
        lineIdx = 0
        while lineIdx < len(lines):
            if lineIdx == len(lines) - 1:
                config.append(lines[lineIdx])
                break

            currIndent = self.getIndent(lineIdx, lines)
            nextIndent = self.getIndent(lineIdx + 1, lines)
            if nextIndent > currIndent:
                key = lines[lineIdx]
                lineIdx += 1
                body = self.getBody(lineIdx, lines)
                config.append({key: self.parse('\n'.join(body))})
                lineIdx += len(body) - 1
            else:
                config.append(lines[lineIdx])
            lineIdx += 1

        return config

    def getIndent(self, posx, lines):
        """
        Returns the indentation level of a line.

        Args:
            posx (int): The index of the line.
            lines (list): List of lines from the configuration.

        Returns:
            int: The number of spaces at the start of the line.
        """
        return len(re.search('^\s*', lines[posx]).group())

    def getBody(self, posx, lines):
        """
        Returns the body of a block of lines with consistent indentation.

        Args:
            posx (int): The starting line index.
            lines (list): List of lines from the configuration.

        Returns:
            list: List of lines that make up the body.
        """
        indent = self.getIndent(posx, lines)
        body = []
        for lineIdx in range(posx, len(lines)):
            currIndent = self.getIndent(lineIdx, lines)
            if currIndent < indent:
                break
            body.append(lines[lineIdx])
        return body

    def query(self, regex, lines=None):
        """
        Recursively searches for lines matching the given regex.

        Args:
            regex (str): The regular expression to search for.
            lines (list, optional): The list of lines to search. Defaults to None.

        Returns:
            list: A list of matching lines or configurations.
        """
        lines = lines or self.config
        result = []
        for item in lines:
            if isinstance(item, dict):
                key = list(item.keys())[0]
                value = list(item.values())[0]
                if re.search(regex, key):
                    result.append(item)
                _result = self.query(regex, value)
                if _result:
                    result.append({key: _result})
            else:
                if re.search(regex, item):
                    result.append(item)
        return result


class AutoParseTextFSM:
    """
    A class for parsing raw string data using TextFSM templates.

    This class provides functionality to parse raw command output using local or NTC templates.
    It supports key-based organization of parsed data and provides error handling and debugging
    through logging.

    Attributes:
        raw_string (str): The raw command output to be parsed.
        cmd (str): The command that generated the raw output.
        device_type (str): The type of device (e.g., "cisco_ios").
        key (str): A key to organize the parsed data, if provided.
    """

    def __init__(self, raw_string, cmd, device_type, key=None):
        """
        Initializes the AutoParseTextFSM instance.

        Args:
            raw_string (str): The raw command output to be parsed.
            cmd (str): The command that generated the raw output.
            device_type (str): The type of device (e.g., "cisco_ios").
            key (str, optional): A key to organize the parsed data. Defaults to None.
        """
        self.raw_string = raw_string
        self.cmd = cmd
        self.device_type = device_type
        self.key = key

    def _get_local_template_paths(self):
        """
        Retrieves the local template directory and index file for TextFSM parsing.

        Returns:
            tuple: A tuple containing the path to the local template directory and the index file.
        """
        template_dir = os.path.join(os.path.dirname(__file__), 'ntc_templates')
        index_file = os.path.join(template_dir, "index")
        return (template_dir, index_file)

    def _get_ntc_template_paths(self):
        """
        Retrieves the NTC template directory and index file for TextFSM parsing.

        Returns:
            tuple: A tuple containing the path to the NTC template directory and the index file.
        """
        packagepath = packages.files(package='ntc_templates')
        template_dir = str(packagepath.parent.joinpath('ntc_templates', 'templates'))
        index_file = os.path.join(template_dir, "index")
        return (template_dir, index_file)

    def parse(self):
        """
        Parses the raw string using TextFSM templates and returns structured data.

        This method first tries to parse the raw string with a local template. If parsing fails,
        it falls back to using NTC templates. If successful, it returns the parsed data as a list
        or a dictionary depending on whether a key is provided.

        Returns:
            list or dict: The parsed data as a list or a dictionary, depending on the presence of `key`.
            If parsing fails, the raw string is returned.
        """
        # Normalize the device type if needed
        device_type = "cisco_ios" if re.search(r'cisco_xe', self.device_type) else self.device_type

        # Retrieve local and NTC template paths
        local_template_dir, local_index_file = self._get_local_template_paths()
        ntc_template_dir, ntc_index_file = self._get_ntc_template_paths()

        table = None

        # First try parsing with local templates
        try:
            if os.path.exists(local_template_dir) and os.path.exists(local_index_file):
                table = CliTable(local_index_file, local_template_dir)
                table.ParseCmd(self.raw_string, {"Command": self.cmd, "Platform": device_type})
            else:
                raise FileNotFoundError("Local template directory or index file not found")
        except Exception:
            # If local parsing fails, try NTC templates
            try:
                table = CliTable(ntc_index_file, ntc_template_dir)
                table.ParseCmd(self.raw_string, {"Command": self.cmd, "Platform": device_type})
            except Exception as ntc_error:
                logging.error(f"Failed to parse command '{self.cmd}' with both local and NTC templates: {ntc_error}")
                return self.raw_string

        # Parse the data into a structured format (list of dictionaries)
        data_list = []
        for row in table:
            row_data = {}
            for index, element in enumerate(row):
                row_data[table.header[index].lower()] = element
            data_list.append(row_data)

        # If a key is provided, return a dictionary keyed by that key
        if self.key:
            keyed_data = {}
            for row in data_list:
                if self.key in row.keys():
                    value = row[self.key]
                    keyed_data[value] = {}
                    for _key, _value in row.items():
                        if _key != self.key:
                            keyed_data[value][_key] = _value
                else:
                    return data_list  # Return the entire list if no key matches
            return keyed_data
        else:
            return data_list  # Return the list if no key is specified

def get_config_section(header, config):
    """
    Extracts and returns the body of a configuration section based on the provided header.

    This function searches for a header in the given configuration string and returns
    the lines of the body under that header until the next header with the same indentation
    level is encountered.

    Args:
        header (str): The header to search for in the configuration.
        config (str): The entire configuration string to search within.

    Returns:
        str: The body of the configuration section under the provided header, as a string.
    """
    # Initialize an empty list to store the body of the configuration under the header
    body_config = []

    # Split the configuration into lines
    config_lines = config.splitlines()

    # Iterate through each line of the config to search for the header
    for line in config_lines:
        # Search for the header (case-insensitive)
        if re.search(r'^\s*' + header + '$', line, flags=re.IGNORECASE):
            # Get the indentation level of the header
            header_indent = re.search(r'^\s*', line).group(0).count(' ')

            # Iterate over the lines after the header to capture the body
            for line_idx in range(config_lines.index(line) + 1, len(config_lines)):
                # Get the indentation level of the current line
                line_indent = re.search(r'^\s*', config_lines[line_idx]).group(0).count(' ')

                # If the current line has the same indentation level as the header, stop the body extraction
                if line_indent == header_indent:
                    break

                # Add the line to the body configuration list
                body_config.append(config_lines[line_idx])

    # Return the body configuration as a joined string with newlines
    return '\n'.join(body_config)
