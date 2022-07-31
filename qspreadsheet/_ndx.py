import logging
import sys
import os
from typing import Dict
from numpy.core.fromnumeric import alltrue
import pandas as pd
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from qspreadsheet.common import DF, SER, pandas_obj_insert_rows, pandas_obj_remove_rows
from qspreadsheet import resources_rc

logger = logging.getLogger(__name__)


class _Ndx():
    VIRTUAL_COUNT = 1

    def __init__(self, index: pd.Index) -> None:
        i_index = range(index.size)
        self._data = self._make_index_data_for(i_index)
        self.is_mutable = False
        self.count_virtual = 0

    @property
    def count_committed(self) -> int:
        """Row count of 'committed' data rows, excluding `in progress` and `virtual` rows, if any"""
        return self._data.index.size - self.count_in_progress - self.count_virtual

    @property
    def count(self) -> int:
        """Row count, excluding `virtual` rows, if any"""
        return self._data.index.size + self.count_virtual

    @property
    def _size(self) -> int:
        """Row count of `committed` + `in_progress` + `virtual` rows"""
        return self._data.index.size

    @property
    def count_in_progress(self) -> int:
        """Row count of the `in progress` rows"""
        return self.in_progress_mask.sum()

    @property
    def in_progress_mask(self) -> SER:
        """`pd.Series[bool]` with the rows/columns in progress"""
        return self._data['in_progress']

    @property
    def disabled_mask(self) -> SER:
        """`pd.Series[bool]` with the disabled rows/columns"""
        return self._data['disabled']

    def set_disabled_mask(self, index, value: bool):
        self._data.loc[index, 'disabled'] = value

    @property
    def non_nullable_mask(self) -> SER:
        """`pd.Series[bool]` with the disabled rows/columns"""
        return self._data['non_nullable']

    def set_non_nullable(self, index, value: bool):
        self._data.loc[index, 'non_nullable'] = value

    def set_disabled_in_progress(self, index, count: int):
        self._data.loc[index, 'disabled_in_progress_count'] = count
        self._update_in_progress(index)

    def set_non_nullable_in_progress(self, index, count: int):
        self._data.loc[index, 'non_nullable_in_progress_count'] = count
        self._update_in_progress(index)

    def reduce_disabled_in_progress(self, index):
        self._data.loc[index, 'disabled_in_progress_count'] -= 1
        self._update_in_progress(index)

    def reduce_non_nullable_in_progress(self, index):
        self._data.loc[index, 'non_nullable_in_progress_count'] -= 1
        self._update_in_progress(index)

    def _update_in_progress(self, index):
        self._data.loc[index, 'in_progress'] = (
            self._data.loc[index, 'disabled_in_progress_count'] +
            self._data.loc[index, 'non_nullable_in_progress_count'] > 0)

    def insert(self, at_index: int, count: int):
        """Inserts rows/columns into the index data"""
        # set new index as 'not in progress' by default
        index = range(at_index, at_index + count)
        new_rows = self._make_index_data_for(index)
        self._data = pandas_obj_insert_rows(
            obj=self._data, at_index=at_index, new_rows=new_rows)

    def remove(self, at_index: int, count: int):
        """Removes rows/columns into the index data"""
        self._data = pandas_obj_remove_rows(
            self._data, at_index, count)
    
    def is_virtual(self, index: int) -> bool:
        return self.count_virtual \
            and index >= self._data.index.size

    @property
    def virtual_enabled(self) -> bool:
        self.count_virtual == self.VIRTUAL_COUNT

    @staticmethod
    def _make_index_data_for(index) -> DF:
        '''Default 'in progress' `DataFrame` to manage the index'''
        return pd.DataFrame(
            data={'in_progress': False, 'disabled': False, 'non_nullable': False,
                  'non_nullable_in_progress_count': 0, 'disabled_in_progress_count': 0},
            index=index)