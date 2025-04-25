# NetCore

**NetCore** is a Python-based toolkit designed for network automation, analysis, and reporting.  
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
from netcore import NetmikoDirect, AutoParseTextFSM, XLBW

# Connect to device
session = NetmikoDirect(hostname="10.1.1.1", username="admin", password="cisco")

# Send command and auto-parse output
parsed_output = session.sendCommand("show ip interface brief", autoParse=True)

# Export to Excel
wb = XLBW("output.xlsx")
wb.dump(parsed_output)
wb.close()
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
