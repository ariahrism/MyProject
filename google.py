import json
import os
import sys
import time

import gspread
from oauth2client.client import SignedJwtAssertionCredentials


def retry(fn):
    def wrapper(*args, **kwargs):
        tries = 3
        while tries > 0:
            try:
                return fn(*args, **kwargs)
            except gspread.AuthenticationError:
                args[0].refresh()
                tries -= 1
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback_template = '''Traceback (most recent call last):
                  File "%(filename)s", line %(lineno)s, in %(name)s
                %(type)s: %(message)s\n'''

                traceback_details = {
                    'filename': exc_traceback.tb_frame.f_code.co_filename,
                    'lineno': exc_traceback.tb_lineno,
                    'name': exc_traceback.tb_frame.f_code.co_name,
                    'type': exc_type.__name__,
                    'message': exc_value.message,  # or see traceback._some_str()
                }

                print 'Error\n' + traceback_template % traceback_details
                tries -= 1

    return wrapper


class NewSession(object):
    client_email = ''
    private_key = ''
    client = None
    workbook = None
    workbook_URL = ''
    worksheet = None
    worksheet_name = ''
    batch_size = 20000

    class _Cell:
        row = 0
        col = 0

        def __init__(self, col, row):
            self.col = col
            self.row = row

    def __init__(self):
        if os.path.isfile('google_key.json'):
            json_key = json.load(open('google_key.json'))
            self.client_email = json_key['client_email']
            self.private_key = json_key['private_key'].encode()
            self._new_auth()
        else:
            json_key = {}
            self.client_email = json_key['client_email']
            self.private_key = json_key['private_key'].encode()
            self._new_auth()

    def _new_auth(self):
        scope = ['https://spreadsheets.google.com/feeds']
        credentials = SignedJwtAssertionCredentials(self.client_email, self.private_key, scope)
        self.client = gspread.authorize(credentials)

    def refresh(self):
        self._new_auth()
        try:
            if self.workbook_URL:
                self.open_workbook(self.workbook_URL)
                if self.worksheet_name:
                    self.open_worksheet(self.worksheet_name)
        except gspread.GSpreadException:
            pass

    @retry
    def open_workbook(self, URL):
        self.workbook_URL = URL
        self.workbook = self.client.open_by_url(self.workbook_URL)

    @retry
    def open_worksheet(self, sheet_name, force=False):
        self.worksheet_name = sheet_name
        try:
            self.worksheet = self.workbook.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            if force:
                self.worksheet = self.workbook.add_worksheet(sheet_name, 1, 1)
            else:
                raise

    @retry
    def append_row(self, list_of_values):
        self.worksheet.append_row(list_of_values)

    @retry
    def clear_sheet(self):
        self.worksheet.resize(cols=self.worksheet.col_count, rows=2)

    @retry
    def _get_selection(self, cols, rows, start_col=1, start_row=1):
        cell_list = None

        start_cell = self._Cell(start_col, start_row)
        end_cell = self._Cell(start_col + cols - 1, start_row + rows - 1)

        row_count = end_cell.row - start_cell.row + 1
        col_count = end_cell.col - start_cell.col + 1
        cell_count = row_count * col_count

        self.worksheet.resize(cols=end_cell.col, rows=end_cell.row if end_cell.row >= self.worksheet.row_count else self.worksheet.row_count)

        if cell_count > self.batch_size:
            # TODO need to write batching
            print 'too big'
            pass
        else:
            print 'cell count', cell_count
            area = self.worksheet.get_addr_int(start_cell.row, start_cell.col) + ':' + self.worksheet.get_addr_int(end_cell.row, end_cell.col)
            cell_list = self.worksheet.range(area)
        # print 'get', type(cell_list)
        return cell_list

    def _rewrite_cell_list(self, input_data, cell_list):
        index = 0
        for row_num, contents in enumerate(input_data):
            for col_num, data in enumerate(input_data[row_num]):
                if type(data) == str:
                    cell_list[index].value = data.encode('utf-8') if data else ''  # may need str(data).decode('utf-8')
                # elif type(data) == unicode:
                #     cell_list[index].value = data.decode('utf-8') if data else ''
                else:
                    cell_list[index].value = data if data else ''

                index += 1
        return cell_list

    def upload_table(self, list_of_lists, start_col=1, start_row=1):
        if len(list_of_lists) == 0:
            list_of_lists = [['']]
        rows = len(list_of_lists)
        cols = len(list_of_lists[0])
        selection = self._get_selection(cols, rows, start_col=start_col, start_row=start_row)
        # print 'selection' , type(selection)
        cell_list_payload = self._rewrite_cell_list(list_of_lists, selection)
        self._upload_data(cell_list_payload)

    def _upload_data(self, cell_list):
        finished = False
        index = 0
        attempts = 5

        while not finished:
            try:
                self.worksheet.update_cells(cell_list[0 + index:self.batch_size + index])
                index += self.batch_size
                if index > len(cell_list):  # need to consider if its exact TODO
                    finished = True
            except:
                attempts -= 1
                if attempts < 1:
                    finished = True
                time.sleep(3)

    def find(self, text):
        try:
            return self.worksheet.find(text)
        except gspread.CellNotFound:
            return None
