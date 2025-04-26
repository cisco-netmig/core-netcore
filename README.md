# Netcore

**Netcore** is a Python-based toolkit designed for network automation, analysis, and reporting.  
It provides a modular framework to connect to devices via SSH, run commands, parse output, and export structured data to Excel.

---

## 🚀 Features

- 🔌 **Terminal Access**  
  Supports direct and proxy SSH access using **Netmiko** and **Paramiko**.

- 🧠 **Command Parsing with TextFSM**  
  Uses NTC templates and custom logic to parse raw command outputs into structured data.

- 📊 **Excel Export**  
  Automatically generate formatted Excel reports with support for custom styles and tables.

- 🔍 **Device Type Auto-Detection**  
  Automatically detects the device platform to apply the correct parsing templates.

---

## 📦 Installation

```bash
pip install git+https://wwwin-github.cisco.com/sanjeekr/netcore.git
# or if packaged
pip install .
```

---

## 🛠 Usage

```python
"""
Example usage of the Netcore toolkit for network automation:
- Establish an SSH session using GenericHandler with support for multiple backends
- Send a command and auto-parse the CLI output using TextFSM
- Export the structured result to an Excel file
"""

from netcore import GenericHandler, XLBW

# Optional proxy (jump server) configuration
proxy = {
    "hostname": "PROXY_IP_ADDRESS",     # e.g., "192.168.100.1"
    "username": "PROXY_USERNAME",       # e.g., "jumpuser"
    "password": "PROXY_PASSWORD"        # e.g., "password123"
}

# Initialize the SSH session using a generic handler (e.g., NETMIKO, PARAMIKO)
session = GenericHandler(
    hostname="DEVICE_IP_ADDRESS",       # e.g., "10.0.1.13"
    username="DEVICE_USERNAME",         # e.g., "admin"
    password="DEVICE_PASSWORD",         # e.g., "admin123"
    proxy=proxy,                        # Optional; remove if not using proxy
    handler="NETMIKO"                   # SSH handler backend: "NETMIKO" or "PARAMIKO"
)

# Send a command and auto-parse the output using TextFSM templates
parsed_output = session.sendCommand(
    "show interface status",
    autoParse=True,
    key="interface"
)

# Export the structured data to an Excel file
wb = XLBW("output.xlsx")                # Output Excel file name
wb.dump(parsed_output)                 # Write parsed data
wb.close()                             # Save and close the workbook
```

---

## 📁 Project Structure

```
netcore/
├── parser.py           # Parsing logic using TextFSM
├── terminal.py         # Terminal handlers for Netmiko, Paramiko
├── xl.py               # Excel export logic
├── ntc_templates/      # Included TextFSM templates
```

---

## 📄 License

MIT License © 2024 Sanjeev Krishna
