"""
This module provides utilities for reading and writing Excel files using `xlsxwriter` and `xlrd`.
It includes enhanced workbook and worksheet classes for formatting, auto column width calculation,
and structured data dumping into Excel files. It also provides functionality to load data
from existing Excel files.

Classes:
    XLBW: Extended xlsxwriter.Workbook with formatting and structured data export.
    XLSW: Custom Worksheet with column width auto-adjustment based on content.
    XLR:  Excel reader using xlrd with flexible header orientation parsing.

Font Dictionary:
    A dictionary that defines a set of predefined cell formats for headers, body, and status messages
    that can be applied to cells in the Excel sheet. These formats include font size, color, alignment,
    background color, and text wrapping properties.

    The dictionary includes:
        - header1, header2, header3, header4: Formats for header rows with varying styles.
        - body: General formatting for body rows.
        - highlight, error, good, bad, info: Formatting styles for specific statuses or messages.
"""

import copy
import json
import re
import os
import logging
from xlsxwriter import Workbook
from xlsxwriter.worksheet import Worksheet
from xlsxwriter.worksheet import convert_cell_args
from xlrd import open_workbook

# Dictionary defining various font styles for headers, body, and status indicators in Excel worksheets.
fonts = {
    "header1": {
        "font_size": "10",
        "font_name": "Segoe UI",
        "align": "center",
        "valign": "top",
        "font_color": "#FFFFFF",
        "bg_color": "#1F4E78",
        "text_wrap": True
    },
    "header2": {
        "font_size": "10",
        "font_name": "Segoe UI",
        "align": "center",
        "valign": "top",
        "font_color": "#000000",
        "bg_color": "#E6E6E6",
        "text_wrap": True
    },
    "header3": {
        "font_size": "10",
        "bold": True,
        "font_name": "Segoe UI",
        "align": "center",
        "valign": "top",
        "text_wrap": True
    },
    "header4": {
        "font_size": "10",
        "align": "center",
        "valign": "top",
        "font_name": "Segoe UI",
        "font_color": "#FFFFFF",
        "bg_color": "#83B159",
        "text_wrap": True
    },
    "body": {
        "font_size": "10",
        "font_name": "Segoe UI",
        "font_color": "#000000",
        "valign": "top",
        "text_wrap": True
    },
    "highlight": {
        "font_name": "Segoe UI",
        "font_size": "10",
        "font_color": "#0082B4",
        "valign": "top",
        "text_wrap": True
    },
    "error": {
        "font_name": "Segoe UI",
        "font_size": "10",
        "font_color": "#F93100",
        "valign": "top",
        "text_wrap": True
    },
    "good": {
        "font_name": "Segoe UI",
        "font_size": "10",
        "font_color": "#006100",
        "bg_color": "#C6EFCE",
        "valign": "top",
        "text_wrap": True
    },
    "bad": {
        "font_name": "Segoe UI",
        "font_size": "10",
        "font_color": "#9C0006",
        "bg_color": "#FFC7CE",
        "valign": "top",
        "text_wrap": True
    },
    "info": {
        "font_name": "Segoe UI",
        "font_size": "10",
        "font_color": "#9C6500",
        "bg_color": "#FFEB9C",
        "valign": "top",
        "text_wrap": True
    }
}


class XLBW(Workbook):
    """
    Extended xlsxwriter.Workbook that supports predefined formats and auto column width management.
    It allows structured dumping of data with support for index and table formatting.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the XLBW workbook and load cell formats from fonts.json.
        """
        super().__init__(*args, **kwargs)
        logging.debug("Initializing XLBW workbook")
        self.create_cell_format()

    def create_cell_format(self):
        """
        Creates and applies cell formats from the predefined `fonts` dictionary.

        Formats are added as workbook attributes using `add_format()`. Logs success or failure.
        """
        try:
            for fmt, params in fonts.items():
                setattr(self, f"ft{fmt}", self.add_format(params))
            logging.debug("Cell formats created successfully")
        except Exception as e:
            logging.error(f"Error loading cell formats: {e}")

    def add_worksheet(self, name=None, worksheet=None):
        """
        Creates and returns a new worksheet using the custom XLSW class.

        This method overrides the default `add_worksheet` to ensure that
        all worksheets are instances of `XLSW`, which includes automatic
        tracking of maximum column widths.

        Args:
            name (str, optional): The name of the worksheet. If None, a default name is assigned.

        Returns:
            XLSW: A customized worksheet instance with extended functionality.
        """
        return super().add_worksheet(name, XLSW)

    def close(self):
        """
        Override close to set appropriate column widths before saving the workbook.
        Gracefully handles scenarios where the workbook file is open in another program.
        """
        logging.debug("Attempting to close workbook and apply column width adjustments.")

        # Set the column widths based on calculated max widths
        for sheet in self.worksheets():
            for col, width in getattr(sheet, 'maxwColumns', {}).items():
                sheet.set_column(col, col, width)

        # Try closing the workbook, prompt user if file is in use
        while True:
            try:
                result = super().close()
                logging.debug(f'Workbook "{self.filename}" closed successfully.')
                return result
            except PermissionError as e:
                logging.error(f'PermissionError: {e}. File "{self.filename}" is likely open elsewhere.')
                input(f'File "{self.filename}" is open in another program. Please close it and press Enter to retry.')
            except Exception as e:
                logging.error(f'Unexpected error while closing workbook: {e}')
                input(f'An error occurred: {e}. Close the file if it\'s open and press Enter to retry.')

    def dump(self, data, worksheet=None, index=None, table=False, row_idx=0, col_idx=0):
        """
        Dump structured data to an Excel worksheet with optional index and table formatting.

        Args:
            data (dict): Data to write.
            worksheet (XLSW, optional): Worksheet to write into.
            index (str, optional): Key name to use as index column.
            table (bool): Whether to format the output as an Excel table.
            row_idx (int): Starting row index.
            col_idx (int): Starting column index.
        """
        logging.debug("Dumping data into worksheet")
        _row_idx = copy.copy(row_idx)
        _col_idx = copy.copy(col_idx)

        if not data:
            logging.debug("No data to write, exiting dump.")
            return

        if not worksheet:
            worksheet = self.add_worksheet()

        if index:
            idx = 0
            indexed_data = {}
            for key, value in data.items():
                idx += 1
                indexed_data[idx] = {index: key}
                indexed_data[idx].update(value)
            data = indexed_data

        if table:
            header_list = [{'header': '#', 'header_format': self.ftheader1}]
            _row_idx += 1
            _col_idx += 1
        else:
            header_list = ['#'] + list(next(iter(data.values())).keys())
            worksheet.write_row(_row_idx, _col_idx, header_list, self.ftheader1)
            worksheet.autofilter(row_idx, col_idx, _row_idx, len(header_list) - 1)
            _row_idx += 1

        for key1, value1 in data.items():
            row_list = [key1]
            for key2, value2 in value1.items():
                if table and {'header': key2, 'header_format': self.ftheader1} not in header_list:
                    header_list.append({'header': key2, 'header_format': self.ftheader1})
                    _col_idx += 1
                if isinstance(value2, list):
                    value2 = '\n'.join(value2)
                elif isinstance(value2, dict):
                    value2 = json.dumps(value2)
                row_list.append(str(value2))
            if table:
                row_idx += 1
                worksheet.write_row(row_idx, col_idx, row_list, self.ftbody)
            else:
                worksheet.write_row(_row_idx, _col_idx, row_list, self.ftbody)
                _row_idx += 1

        if table:
            worksheet.add_table(row_idx, col_idx, _row_idx - 1, _col_idx - 1, {'columns': header_list, 'style': None})
            logging.debug("Excel table added with headers")


class XLSW(Worksheet):
    """
    Custom xlsxwriter.Worksheet that tracks maximum column widths for dynamic resizing.
    """

    def __init__(self):
        """
        Initialize the worksheet and setup max width tracking.
        """
        super().__init__()
        self.maxwColumns = {}

    def get_max_width(self, cell_value):
        """
        Estimate width of a cell content based on characters.

        Args:
            cell_value (str): The cell content.

        Returns:
            float: Estimated column width.
        """
        lines = list(map(str.rstrip, str(cell_value).splitlines()))
        maxline = max(lines, key=len) if lines else ''
        width = 0
        for char in maxline:
            width += 1.4 if char.isupper() else 1.1
        return width

    def set_column_width(self, first_col, last_col, width):
        """
        Set fixed width for a range of columns.

        Args:
            first_col (int): Start column index.
            last_col (int): End column index.
            width (float): Width to set.
        """
        for col in range(first_col, last_col + 1):
            self.maxwColumns[col] = width

    @convert_cell_args
    def _write(self, row, col, string, cell_format=None):
        """
        Write to cell while calculating and updating max column width.

        Args:
            row (int): Row index.
            col (int): Column index.
            string (str): Value to write.
            cell_format (Format, optional): Format to apply.

        Returns:
            int: Result from the write operation.
        """
        if self._check_dimensions(row, col):
            return -1
        string_width = self.get_max_width(string)
        max_width = self.maxwColumns.get(col, 0)
        if string_width > max_width:
            self.maxwColumns[col] = string_width
        if re.match(r'^=', str(string)):
            return self.write_string(row, col, str(string), cell_format)
        return super()._write(row, col, string, cell_format)


class XLR:
    """
    Excel file reader using xlrd with support for vertical or horizontal headers.
    """

    def __init__(self, filename):
        """
        Initialize the reader with the given Excel file.

        Args:
            filename (str): Path to the Excel file.
        """
        self.book = open_workbook(filename)
        logging.debug(f"Opened Excel file for reading: {filename}")

    def load(self, vheader=False, hheader=False):
        """
        Load data from the Excel file with optional header orientation.

        Args:
            vheader (bool): Use first column as vertical headers.
            hheader (bool): Use first row as horizontal headers.

        Returns:
            dict: Loaded data organized by sheet names.
        """
        return_data = {}
        for sheet in range(self.book.nsheets):
            ws = self.book.sheet_by_index(sheet)
            data = {}

            if vheader:
                for i in range(ws.nrows):
                    data[ws.cell_value(i, 0)] = [ws.cell_value(i, j) for j in range(1, ws.ncols)]
            elif hheader:
                for i in range(1, ws.nrows):
                    row_key = ws.cell_value(i, 0)
                    data[row_key] = {ws.cell_value(0, j): ws.cell_value(i, j) for j in range(1, ws.ncols)}
            else:
                for i in range(ws.ncols):
                    col_key = ws.cell_value(0, i)
                    data[col_key] = [ws.cell_value(j, i) for j in range(1, ws.nrows)]

            return_data[ws.name] = data
            logging.debug(f"Loaded data from sheet: {ws.name}")

        return return_data
