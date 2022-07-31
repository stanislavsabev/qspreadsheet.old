import logging
from os import truncate
import sys
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from pandas.core.series import Series

from qspreadsheet.common import DF, SER, pandas_obj_insert_rows, pandas_obj_remove_rows
from qspreadsheet.delegates import MasterDelegate
from qspreadsheet.header_view import HeaderView
from qspreadsheet._ndx import _Ndx
from qspreadsheet import resources_rc

logger = logging.getLogger(__name__)


class DataFrameModel(QAbstractTableModel):

    mutable_rows_enabled = Signal(bool)
    virtual_rows_enabled = Signal(bool)

    def __init__(self, df: DF, header_view: HeaderView,
                 delegate: MasterDelegate, parent: Optional[QWidget] = None) -> None:
        QAbstractTableModel.__init__(self, parent=parent)
        self.delegate = delegate
        self._init_data(df)

        non_nullables = list(self.delegate.non_nullable_delegates.keys())
        if non_nullables:
            self.col_ndx.set_non_nullable(non_nullables, True)
            
        self.header_view = header_view
        
        self.is_dirty = False

        self.dataChanged.connect(self.on_dataChanged)
        self.rowsInserted.connect(self.on_rowsInserted)
        self.rowsRemoved.connect(self.on_rowsRemoved)

    def _init_data(self, df: DF):
        self._df = df.copy()
        self.row_ndx = _Ndx(self._df.index)
        self.col_ndx = _Ndx(self._df.columns)
        # freeze columns
        self.row_ndx.is_mutable = True
        self.row_ndx.count_virtual = _Ndx.VIRTUAL_COUNT

    @property
    def df(self):
        # TODO: FIXME: self.col_ndx.in_progress_mask.values
        # NOTE: converting to 'values' array is needed because
        # the column index is not numeric, so it maybe be better
        # to make the row and column index datatype agnostic
        not_inprogress_rows = ~self.row_ndx.in_progress_mask
        not_inprogress_columns = ~self.col_ndx.in_progress_mask.values
        return self._df.loc[not_inprogress_rows, not_inprogress_columns].copy()

    def columnCount(self, parent: QModelIndex) -> int:
        return self.col_ndx.count

    def rowCount(self, parent: QModelIndex) -> int:
        return self.row_ndx.count

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        # logger.debug('data({}, {}), role: {}'.format( index.row(), index.column(), role))
        if index.row() < 0:
            logger.error('index.row() < 0')
            return None
        
        if role == Qt.DisplayRole:
            if self.row_ndx.is_virtual(index.row()):
                return ''
            value = self._df.iloc[index.row(), index.column()]
            return self.delegate.display_data(index, value)

        if role == Qt.EditRole:
            if self.row_ndx.is_virtual(index.row()):
                return self.delegate.default_value(index)
            value = self._df.iloc[index.row(), index.column()]
            return value

        if role == Qt.TextAlignmentRole:
            return int(self.delegate.alignment(index))

        if role == Qt.BackgroundRole:
            if self.flags(index) & Qt.ItemIsEditable:
                return self.delegate.background_brush(index)
            return QApplication.palette().alternateBase()

        if role == Qt.ForegroundRole:
            if self.row_ndx.is_virtual(index.row()) \
                    or self.col_ndx.is_virtual(index.column()):
                return self.delegate.foreground_brush(index)

            if self.row_ndx.in_progress_mask.iloc[index.row()] \
                    and self.col_ndx.disabled_mask.iloc[index.column()]:
                return QColor(255, 0, 0)

            if self.row_ndx.in_progress_mask.iloc[index.row()] \
                    and self.col_ndx.non_nullable_mask.iloc[index.column()]:
                    
                value = self._df.iloc[index.row(), index.column()]
                if pd.isnull(value):
                    return QColor(255, 0, 0)

            return self.delegate.foreground_brush(index)

        if role == Qt.FontRole:
            return self.delegate.font(index)

        return None

    def setData(self, index: QModelIndex, value: Any, role=Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        # If user has typed in the last row
        if self.row_ndx.is_virtual(index.row()):
            self.insertRow(index.row(), QModelIndex())

        # if self.col_ndx.is_virtual(index.column()):
        #     self.insertColumn(self.col_ndx.count, QModelIndex())

        self._df.iloc[index.row(), index.column()] = value

        # update rows in progress
        if self.row_ndx.in_progress_mask.iloc[index.row()]:
            if self.col_ndx.disabled_mask.iloc[index.column()]:
                self.row_ndx.reduce_disabled_in_progress(index.row())

            if self.col_ndx.non_nullable_mask.iloc[index.column()]:
                value = self._df.iloc[index.row(), index.column()]
                if not pd.isnull(value):
                    self.row_ndx.reduce_non_nullable_in_progress(index.row())

        self.dataChanged.emit(index, index)
        return True

    def headerData(self, section: int, orientation: Qt.Orientation, role: int) -> Any:

        if section < 0:
            logger.error('section: {}'.format(section))
            return None

        if orientation == Qt.Vertical:
            is_virtual = self.row_ndx.is_virtual(section)
            if role == Qt.DisplayRole:
                if is_virtual:
                    return '*'
                return str(self._df.index[section])
            if role == Qt.ForegroundRole:
                if is_virtual:
                    return None
                if self.row_ndx.in_progress_mask.iloc[section]:
                    return QColor(255, 0, 0)
                return None
            return None

        if orientation == Qt.Horizontal:
            is_virtual = self.col_ndx.is_virtual(section)
            if role == Qt.DisplayRole:
                if is_virtual:
                    return '*'
                return self.header_view.header_widgets[section]
            return None
        return None

    def insertRows(self, row: int, count: int, parent: QModelIndex) -> bool:
        if self.row_ndx.is_mutable == False:
            logger.error('Calling `insertRows` on immutable row index.')
            return False

        self.beginInsertRows(QModelIndex(), row, row + count - 1)

        new_rows = self.null_rows(start_index=row, count=count)
        self._df = pandas_obj_insert_rows(self._df, row, new_rows)

        self.endInsertRows()
        self.dataChanged.emit(self.index(row, 0), self.index(
            row + count, self.col_ndx._size))
        return True

    def removeRows(self, row: int, count: int, parent: QModelIndex) -> bool:
        if self.row_ndx.is_mutable == False:
            logger.error('Calling `removeRows` on immutable row index.')
            return False

        # logger.debug('removeRows(first:{}, last:{}), num rows: {}'.format(
        #     row, row + count - 1, count))
        self.beginRemoveRows(parent, row, row + count - 1)
        self._df = pandas_obj_remove_rows(self._df, row, count)
        self.endRemoveRows()
        self.dataChanged.emit(self.index(
            row, 0), self.index(row, self.col_ndx._size))
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        flag = QAbstractTableModel.flags(self, index)

        if self.row_ndx.is_virtual(index.row()):
            return flag | Qt.ItemIsEditable

        if self.row_ndx.is_mutable and self.row_ndx.in_progress_mask.iloc[index.row()]:
            return flag | Qt.ItemIsEditable

        if not self.col_ndx.disabled_mask.iloc[index.column()]:
            return flag | Qt.ItemIsEditable

        return flag

    def on_horizontal_scroll(self, dx: int):
        self.header_view.fix_item_positions()

    def enable_mutable_rows(self, enable: bool):
        if self.row_ndx.is_mutable == enable:
            return
        self.row_ndx.is_mutable = enable
        self.mutable_rows_enabled.emit(enable)

    def enable_virtual_row(self, enable: bool):
        if self.row_ndx.virtual_enabled == enable:
            return
        self.beginResetModel()
        self.row_ndx.count_virtual = (_Ndx.VIRTUAL_COUNT if enable else 0)
        self.endResetModel()
        self.virtual_rows_enabled.emit(enable)
    
    def set_read_only(self, readonly):
        self.enable_mutable_rows(readonly)
        self.enable_virtual_row(readonly)

    def add_virtual_row(self):
        at_index = self._df.index.size
        bottom_row = self.null_rows(start_index=at_index, count=1)
        self._df = self._df.append(bottom_row)
        self.row_ndx.insert(at_index, 1)

    def add_virtual_column(self):
        at_index = self._df.columns.size
        self._df['__virtual_column__'] = None
        self.col_ndx.insert(at_index, 1)        

    def null_rows(self, start_index: int, count: int) -> DF:
        nulls_row: Dict[int, Any] = self.delegate.null_value()
        data = {self._df.columns[ndx]: null_value
                for ndx, null_value in nulls_row.items()}

        nulls_df = pd.DataFrame(data=data,
                                index=range(start_index, start_index + count))
        return nulls_df

    def on_dataChanged(self, first: QModelIndex, last: QModelIndex, roles):
        self.is_dirty = True

    def on_rowsInserted(self, parent: QModelIndex, first: int, last: int):
        self.is_dirty = True
        self.row_ndx.insert(at_index=first, count=last - first + 1)

        rows_inserted = list(range(first, last + 1))

        # If there are disabled columns, all inserted rows
        # gain 'row in progress' status
        if self.col_ndx.disabled_mask.any():
            self.row_ndx.set_disabled_in_progress(
                rows_inserted, self.col_ndx.disabled_mask.sum())

        if self.col_ndx.non_nullable_mask.any():
            self.row_ndx.set_non_nullable_in_progress(
                rows_inserted, self.col_ndx.non_nullable_mask.sum())

    def on_rowsRemoved(self, parent: QModelIndex, first: int, last: int):
        self.is_dirty = True
        self.row_ndx.remove(at_index=first, count=last - first + 1)

    def sort(self, column_index: int, order: Qt.SortOrder) -> None:
        """Sort table by given column number.
        """
        self.layoutAboutToBeChanged.emit()
        
        ascending = True if order == Qt.AscendingOrder else False
        column_name = self._df.columns[column_index]
        real_rows = self._df.iloc[ : self.row_ndx.count]
        virtual_rows = self._df.iloc[self.row_ndx.count : ]
        real_rows = real_rows.sort_values(by=column_name, ascending=ascending, ignore_index=truncate)
        self._df = real_rows.append(virtual_rows)

        self.layoutChanged.emit()
