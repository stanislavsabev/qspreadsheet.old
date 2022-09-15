import logging
from logging import log
import os
import traceback

from numpy.lib.function_base import disp
from qspreadsheet.worker import Worker

from numpy.core.fromnumeric import alltrue, size
from qspreadsheet.dataframe_model import DataFrameModel
import sys
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from qspreadsheet import resources_rc
from qspreadsheet.common import DF, SER
from qspreadsheet.common import pandas_obj_insert_rows
from qspreadsheet.common import pandas_obj_remove_rows
from qspreadsheet._ndx import _Ndx
from qspreadsheet.menus import FilterWidgetAction

logger = logging.getLogger(__name__)

INITIAL_FILTER_LIMIT = 5000
FILTER_VALUES_STEP = 5000
DEFAULT_FILTER_INDEX = -1


class DataFrameSortFilterProxy(QSortFilterProxyModel):

    column_filtered = Signal(int)
    column_unfiltered = Signal(int)

    def __init__(self, model: DataFrameModel, parent: Optional[QWidget]=None) -> None:
        super(DataFrameSortFilterProxy, self).__init__(parent)
        self._model: DataFrameModel = model
        self._model.rowsInserted.connect(self.on_rows_inserted)
        self._model.rowsRemoved.connect(self.on_rows_removed)

        self._column_index = 0
        self._filter_widget = None
        self._pool = QThreadPool(self)

        self._display_values: Optional[SER] = None
        self._filter_values: Optional[SER] = None
        self._display_values_gen = None
        self._showing_all_display_values = False
        self.filter_cache: Dict[int, SER] = {
            DEFAULT_FILTER_INDEX : self.alltrues() }
        self.accepted = self.filter_cache[DEFAULT_FILTER_INDEX].copy()

    def create_filter_widget(self) -> FilterWidgetAction:
        if self._filter_widget:
            self._filter_widget.deleteLater()
        self._filter_widget = FilterWidgetAction()
        self._filter_widget.show_all_btn.clicked.connect(
            self.async_refill_list)
        return self._filter_widget

    def add_filter_mask(self, mask: SER):
        if self._column_index in self.filter_cache:
            self.filter_cache.pop(self._column_index)
        self.filter_cache[self._column_index] = mask
        # update accepted
        self._update_accepted(mask)
        self.column_filtered.emit(self._column_index)

    def remove_filter_mask(self, column_index):
        if column_index in self.filter_cache:
            self.filter_cache.pop(column_index)
        self._update_accepted(self.filter_mask)
        self.column_unfiltered.emit(self._column_index)

    def _update_accepted(self, mask: SER):
        self.accepted.loc[:] = False
        self.accepted.loc[mask.index] = mask

    def string_filter(self, text: str):
        values, _ = self.get_model_values()

        self._display_values = pd.Series({
            ndx : self._model.delegate.display_data(self._model.index(ndx, self._column_index), value)
            for ndx, value in values.items()})
        self._showing_all_display_values = True

        if text:
            mask = self._display_values.str.lower().str.contains(text.lower())
        else:
            mask = pd.Series(data=True, index=self._display_values.index)

        self.add_filter_mask(mask)
        self.invalidateFilter()

    def filter_list_widget_by_text(self, text: str):
        self._filter_widget.clear()
        if text:
            mask = self._filter_values.str.lower().str.contains(text.lower())
            filter_values = self._filter_values.loc[mask]
            if filter_values.size == 0:
                return

            for _, value in filter_values.items():
                item = QListWidgetItem(value)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self._filter_widget.addItem(item)

            state = Qt.Checked
        else:
            mask = self.filter_mask
            filter_values = self._filter_values
            self.add_list_items(filter_values, mask)
            state = Qt.Checked if mask.all() else Qt.Unchecked

        self._filter_widget.addSelectAllItem(state)
        self._filter_widget.all_deselected.emit(False)

    def apply_list_filter(self, menu):
        if self._filter_widget.list.count() == 0:
            return

        text = self._filter_widget.str_filter.lineEdit.text()
        checked = self._filter_widget.select_all_item.checkState() == Qt.Checked
        is_filtered = self.is_column_filtered(self._column_index)
        # START HERE 
        if checked and is_filtered and not text:
            self.remove_filter_mask(self._column_index)
        elif checked and not is_filtered and not text:
            return
        else:
            checked_values = [s.lower() for s in self._filter_widget.values()]
            if not self._showing_all_display_values:
                display_values = pd.Series({ndx : value for ndx, value in self._display_values_gen})
                self._display_values = self._display_values.append(display_values)
                self._showing_all_display_values = True

            mask = self._display_values.str.lower().isin(checked_values)
            self.add_filter_mask(mask)
        self.invalidateFilter()

    def clear_filter_cache(self):
        if not self.is_data_filtered:
            return
        indices = [index for index in self.filter_cache if index != DEFAULT_FILTER_INDEX]
        
        self.filter_cache.clear()
        self.filter_cache = { DEFAULT_FILTER_INDEX : self.alltrues() }
        self.accepted = self.filter_cache[DEFAULT_FILTER_INDEX].copy()
        self._column_index = self.last_filter_index
        self.invalidateFilter()

        for index in indices:
            self.column_unfiltered.emit(index)

    def clear_filter_from_column(self, column_index: int):
        self.remove_filter_mask(column_index)
        if self._column_index == column_index:
            self._column_index = self.last_filter_index
        self.invalidateFilter()

    def refill_list(self, *args, **kwargs):
        """ Adds to the filter list all remaining values,
            over the initial filter limit

            NOTE: *args, **kwargs signature is required by Worker
        """
        display_values = pd.Series({ndx : value for ndx, value in self._display_values_gen})
        self._display_values = self._display_values.append(display_values)
        self._showing_all_display_values = True
        # Updating filter_values
        filter_index = display_values.str.lower().drop_duplicates().index
        filter_values = display_values.loc[filter_index]
        self._filter_values = self._filter_values.append(filter_values)
        self.add_list_items(filter_values, self.accepted)

    def async_populate_list(self):
        worker = Worker(func=self.populate_list)
        worker.signals.error.connect(self.parent().on_error)
        # worker.run()
        self._pool.start(worker)

    def populate_list(self, *args, **kwargs):
        self._filter_widget.clear()
        model_values, mask = self.get_model_values()

        # Generator for display filter values
        self._display_values_gen = (
            (ndx ,self._model.delegate.display_data(self._model.index(ndx, self._column_index), value))
            for ndx, value in model_values.items())

        if model_values.size <= INITIAL_FILTER_LIMIT:
            self._display_values = pd.Series({ndx : value for ndx, value in self._display_values_gen})
            self._showing_all_display_values = True
            filter_index = self._display_values.str.lower().drop_duplicates().index
            self._filter_values = self._display_values.loc[filter_index]
        else:
            self._display_values = pd.Series(name=model_values.name)
            self._filter_values = pd.Series(name=model_values.name)

            next_step = INITIAL_FILTER_LIMIT
            remaining = model_values.size

            while next_step and self._filter_values.size < INITIAL_FILTER_LIMIT:
                # print('next_step {}, remaining {}'.format(next_step, remaining))
                to_display = pd.Series(dict(next(self._display_values_gen)
                                for _ in range(next_step)))
                self._display_values = self._display_values.append(to_display)
                filter_index = to_display.str.lower().drop_duplicates().index
                self._filter_values = self._filter_values.append(to_display.loc[filter_index])
                remaining -= next_step
                remaining = max(remaining, 0)
                next_step = min(FILTER_VALUES_STEP, remaining)

            if remaining:
                self._filter_widget.show_all_btn.setVisible(True)
                self._showing_all_display_values = False
            else:
                self._showing_all_display_values = True

        # Add a (Select All)
        if mask.all():
            select_all_state = Qt.Checked
        else:
            select_all_state = Qt.Unchecked

        self._filter_widget.addSelectAllItem(select_all_state)
        self.add_list_items(self._filter_values, self.accepted)

    def add_list_items(self, values: SER, checked_mask: SER):
        """values : {pd.Series}: values to add to the list
        """

        for row_ndx, value in values.items():
            state = Qt.Checked if checked_mask.loc[row_ndx] else Qt.Unchecked
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(state)
            self._filter_widget.addItem(item)
        # self._list_widget.list.sortItems()

    def async_refill_list(self):
        btn = self.sender()
        worker = Worker(func=self.refill_list)
        worker.signals.error.connect(self.parent().on_error)
        worker.signals.result.connect(lambda: btn.setVisible(False))
        worker.signals.about_to_start.connect(lambda: btn.setEnabled(False))
        worker.signals.finished.connect(lambda: btn.setEnabled(True))
        # worker.run()
        self._pool.start(worker)

    def get_model_values(self) -> Tuple[SER, SER]:
        # Generates filter items for given column index
        column: SER = self._model.df.iloc[:, self._column_index]
        filter_mask = self.filter_mask

        # if the column being filtered is not the last filtered column
        if self._column_index != self.last_filter_index:
            filter_mask = filter_mask.loc[filter_mask]
            column = column.loc[filter_mask.index]
        column = column.sort_values()
        return column, filter_mask

    @property
    def filter_key_column(self) -> int:
        return self._column_index

    def set_filter_key_column(self, value: int):
        self._column_index = value

    @property
    def is_data_filtered(self) -> bool:
        return len(self.filter_cache) > 1

    @property
    def filter_mask(self) -> SER:
        return self.filter_cache[self.last_filter_index]

    @property
    def last_filter_index(self) -> int:
        return list(self.filter_cache.keys())[-1]

    def is_column_filtered(self, col_ndx: int) -> bool:
        return col_ndx in self.filter_cache

    def alltrues(self) -> pd.Series:
        return pd.Series(data=True, index=self._model.df.index)

    def on_rows_inserted(self, parent: QModelIndex, first: int, last: int):
        new_rows = pd.Series(data=True, index=range(first, last + 1))
        for index, mask in self.filter_cache.items():
            mask = pandas_obj_insert_rows(mask, first, new_rows)
            self.filter_cache[index] = mask
        self.accepted = pandas_obj_insert_rows(self.accepted, first, new_rows)

    def on_rows_removed(self, parent: QModelIndex, first: int, last: int):
        count = last - first + 1
        for index, mask in self.filter_cache.items():
            mask = pandas_obj_remove_rows(mask, first, count)
            self.filter_cache[index] = mask
        self.accepted = pandas_obj_remove_rows(self.accepted, first, count)

# region Overloads

    def sort(self, column: int, order: Qt.SortOrder):
        self.sourceModel().sort(column, order)
        
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if source_row < self.accepted.size:
            return self.accepted.iloc[source_row]
        return True

# endregion Overloads