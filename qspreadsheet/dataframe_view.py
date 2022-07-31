import logging
import os
import sys
import traceback
from functools import partial
from itertools import count, groupby
from types import TracebackType
from typing import (Any, Iterable, List, Mapping, Optional, Tuple, Type, Union)
import numpy as np
import pandas as pd
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from qspreadsheet import resources_rc
from qspreadsheet.common import DF, is_iterable, standard_icon
from qspreadsheet.custom_widgets import ActionButtonBox
from qspreadsheet.dataframe_model import DataFrameModel
from qspreadsheet.delegates import (ColumnDelegate, MasterDelegate,
                                    automap_delegates)
from qspreadsheet.header_view import HeaderView, HeaderWidget
from qspreadsheet.sort_filter_proxy import DataFrameSortFilterProxy
from qspreadsheet.worker import Worker

logger = logging.getLogger(__name__)


class DataFrameView(QTableView):
    '''`QTableView` to display and edit `pandas.DataFrame`

        Parameters
        ----------

        df : `pandas.DataFrame`. The data frame to manage

        delegates : [ Mapping[column, ColumnDelegate] ].  Default is 'None'.

        Column delegates used to display and edit the data.

        If no delegates are provided, `automap_delegates(df, nullable=True)` is used
        to guess the delegates, based on the column type.

        parent : [ QWidget ].  Default is 'None'. Parent for this view.
    '''

    def __init__(self, df: DF, delegates: Optional[Mapping[Any, ColumnDelegate]] = None, parent=None) -> None:
        super(DataFrameView, self).__init__(parent)
        self.threadpool = QThreadPool(self)
        self.header_view = HeaderView(columns=df.columns.astype(str))
        self.header_view.setSectionsClickable(True)
        self.setHorizontalHeader(self.header_view)
        self.header_view.filter_btn_mapper.mapped[str].connect(
            self.filter_clicked)

        self._main_delegate = MasterDelegate(self)
        column_delegates = delegates or automap_delegates(df, nullable=True)
        self._set_column_delegates_for_df(column_delegates, df)

        self._model = DataFrameModel(df=df, header_view=self.header_view,
                                     delegate=self._main_delegate, parent=self)

        self._proxy = DataFrameSortFilterProxy(model=self._model, parent=self)
        self._proxy.setSourceModel(self._model)
        self.setModel(self._proxy)
        self._proxy.column_filtered.connect(lambda col_ndx: 
            self.header_view.header_widgets[col_ndx].set_filtered(True))
        self._proxy.column_unfiltered.connect(lambda col_ndx: 
            self.header_view.header_widgets[col_ndx].set_filtered(False))

        self.horizontalScrollBar().valueChanged.connect(self._model.on_horizontal_scroll)
        self.set_column_widths()

    def sizeHint(self) -> QSize:
        width = 0
        for i in range(self._df.shape[1]):
            width += self.columnWidth(i)
        width += self.verticalHeader().sizeHint().width()
        width += self.verticalScrollBar().sizeHint().width()
        width += self.frameWidth() * 2

        return QSize(width, self.height())

    def contextMenuEvent(self, event: QContextMenuEvent):
        '''Implements right-clicking on cell.

            NOTE: You probably want to overrite make_cell_context_menu, not this
            function, when subclassing.
        '''
        row_ndx = self.rowAt(event.y())
        col_ndx = self.columnAt(event.x())

        if row_ndx < 0 or col_ndx < 0:
            return  # out of bounds

        menu = self.make_cell_context_menu(row_ndx, col_ndx)

        pos = self.mapToGlobal(event.pos())
        menu_pos = QPoint(pos.x() + 20,
                          pos.y() + menu.height() + 20)
        menu.exec_(menu_pos)

    def set_columns_edit_state(self, columns: Union[Any, Iterable[Any]], edit_state: bool) -> None:
        '''Enables/disables column's edit state.
            NOTE: By default all columns are editable

            Paramenters
            -----------
            columns : column or list-like. Columns to enable/disable

            editable : bool. Edit state for the columns
        '''

        if not is_iterable(columns):
            columns = [columns]

        missing = [column for column in columns
                   if column not in self._df.columns]
        if missing:
            plural = 's' if len(missing) > 1 else ''
            raise ValueError('Missing column{}: `{}`.'.format(
                plural, '`, `'.join(missing)))

        column_indices  = self._model._df.columns.get_indexer(columns)
        self._model.col_ndx.set_disabled_mask(column_indices, (not edit_state))

    def set_column_delegate_for(self, column: Any, delegate: ColumnDelegate):
        '''Sets the column delegate for single column

            Paramenters
            -----------
            columns : Any. Column to set delegate for

            editable : ColumnDelegate. The delegate for the column
        '''
        icolumn = self._df.columns.get_loc(column)
        self._main_delegate.add_column_delegate(icolumn, delegate)

    def _set_column_delegates_for_df(self, delegates: Mapping[Any, ColumnDelegate], df: DF):
        '''(Private) Used to avoid circular reference, when calling self._temp_df
        '''
        current = self.itemDelegate()
        if current is not None:
            current.deleteLater()

        for column, column_delegate in delegates.items():
            column_delegate.setObjectName(str(column))
            icolumn = df.columns.get_loc(column)
            self._main_delegate.add_column_delegate(icolumn, column_delegate)

        self.setItemDelegate(self._main_delegate)
        
        del current

    def set_column_delegates(self, delegates: Mapping[Any, ColumnDelegate]):
        '''Sets the column delegates for multiple columns

            Paramenters
            -----------
            delegates : Mapping[column, ColumnDelegate]. Dict-like, with column name and delegates
        '''
        self._set_column_delegates_for_df(delegates, self._model._df)

    def set_column_widths(self):
        header = self.horizontalHeader()
        for i in range(header.count()):
            header.resizeSection(
                i, self.header_view.header_widgets[i].sizeHint().width())

    def enable_mutable_rows(self, enable: bool):
        if not isinstance(enable, bool):
            raise TypeError('Argument `muttable` not a boolean.')
        self._model.enable_mutable_rows(enable=enable)

    def enable_virtual_row(self, enable: bool):
        self._model.enable_virtual_row(enable)
    
    def set_read_only(self, readonly):
        self._model.set_read_only(readonly)

    @property
    def df(self) -> pd.DataFrame:
        """DataFrameModel's result DataFrame 
            (WITHOUT the rows and columns in progress)
        """        
        return self._model.df

    @property
    def _df(self) -> pd.DataFrame:
        """DataFrameModel's temp DataFrame 
            (INCLUDING the rows and columns in progress)
        """
        return self._model._df

    def filter_clicked(self, name: str):
        btn: QPushButton = self.sender().mapping(name)
        header_widget: HeaderWidget = btn.parent()

        col_ndx = self.header_view.header_widgets.index(header_widget)
        self._proxy.set_filter_key_column(col_ndx)

        # TODO: look for other ways to position the menu
        header_pos = self.mapToGlobal(header_widget.pos())
        self.header_menu = self.make_header_menu(col_ndx, header_widget)

        menu_pos = QPoint(header_pos.x() + self.header_menu.width() - btn.width() + 5,
                        header_pos.y() + btn.height() + 15)
        # menu.move(menu_pos.x(), menu_pos.y())    
        # menu.show()
        self.header_menu.exec_(menu_pos)

    def make_cell_context_menu(self, row_ndx: int, col_ndx: int) -> QMenu:
        menu = QMenu(self)
        self._proxy.set_filter_key_column(col_ndx)
        
        # By Value Filter
        menu.addAction(standard_icon('CommandLink'),
                       "Filter By Value", partial(self.filter_by_value, row_ndx, col_ndx))

        # GreaterThan/LessThan filter
        # def _cmp_filter(s_col, op):
        #     return op(s_col, cell_val)
        # menu.addAction("Filter Greater Than",
        #                 partial(self._data_model.filterFunction, col_ndx=col_ndx,
        #                         function=partial(_cmp_filter, op=operator.ge)))
        # menu.addAction("Filter Less Than",
        #                 partial(self._data_model.filterFunction, col_ndx=col_ndx,
        #                         function=partial(_cmp_filter, op=operator.le)))
        menu.addAction(standard_icon('DialogResetButton'),
                    "Clear Filter",
                    self.clear_all_filters).setEnabled(self._proxy.is_data_filtered)

        header_widget = self.header_view.header_widgets[col_ndx]
        menu.addAction(standard_icon('DialogResetButton'),
                    f"Clear Filter from `{header_widget.short_text}`",
                    partial(self.clear_column_filter, col_ndx)
                    ).setEnabled(self._proxy.is_column_filtered(col_ndx))
                                              
        menu.addSeparator()

        if self._model.row_ndx.is_mutable:
            menu.addAction("Insert Rows Above",
                        partial(self.insert_rows, 'above'))
            menu.addAction("Insert Rows Below",
                        partial(self.insert_rows, 'below'))
            menu.addSeparator()
            menu.addAction("Deleted Selected Rows",
                        self.remove_rows)
                        
        menu.addSeparator()

        # Open in Excel
        menu.addAction("Open in Excel...", self.async_to_excel)
        return menu

    def make_header_menu(self, col_ndx: int, header_widget: HeaderWidget) -> QMenu:
        '''Create popup menu used for header'''

        menu = QMenu(self)
        filter_widget = self._proxy.create_filter_widget()
        self._proxy.set_filter_key_column(col_ndx)
        filter_widget.setParent(self)

        # Filter Menu Action
        filter_widget.str_filter.returnPressed.connect(self.apply_and_close_header_menu)
        filter_widget.str_filter.textChanged.connect(self.filter_list_widget_by_text)

        self._proxy.set_filter_key_column(col_ndx)
        self._proxy.async_populate_list()

        menu.addAction(filter_widget)

        menu.addAction(standard_icon('DialogResetButton'),
                    "Clear Filter",
                    self.clear_all_filters).setEnabled(self._proxy.is_data_filtered)
        menu.addAction(standard_icon('DialogResetButton'),
                       f"Clear Filter from `{header_widget.short_text}`",
                       partial(self.clear_column_filter, col_ndx)
                       ).setEnabled(self._proxy.is_column_filtered(col_ndx))
        
        # Sort Ascending/Decending Menu Action
        menu.addAction(standard_icon('TitleBarShadeButton'),
                       "Sort Ascending",
                       partial(self.model().sort, col_ndx, Qt.AscendingOrder))
        menu.addAction(standard_icon('TitleBarUnshadeButton'),
                       "Sort Descending",
                       partial(self.model().sort, col_ndx, Qt.DescendingOrder))

        menu.addSeparator()

        # Hide
        menu.addAction("Hide Column", partial(self.hideColumn, self._proxy.filter_key_column))

        # Unhide column to left and right
        for i in (-1, 1):
            ndx = self._proxy.filter_key_column + i
            if self.isColumnHidden(ndx):
                menu.addAction(f'Unhide {self._df.columns[ndx]}',
                               partial(self.showColumn, ndx))

        # Unhide all hidden columns
        def _unhide_all(hidden_indices: list):
            for ndx in hidden_indices:
                self.showColumn(ndx)
        hidden_indices = self._get_hidden_column_indices()
        if hidden_indices:
            menu.addAction(f'Unhide All',
                           partial(_unhide_all, hidden_indices))

        menu.addSeparator()

        # Filter Button box
        action_btn_box = ActionButtonBox(menu)
        action_btn_box.btn_ok.clicked.connect(self.apply_and_close_header_menu)
        action_btn_box.btn_cancel.clicked.connect(menu.close)
        
        self._proxy._filter_widget.all_deselected.connect(action_btn_box.disableOkayButton)
        menu.addAction(action_btn_box)
        return menu

    def insert_rows(self, direction: str):
        if not self._model.row_ndx.is_mutable:
            logger.warning('Calling `insert_rows` on immutable row index')
            return
            
        indexes: List[QModelIndex] = self.selectionModel().selectedIndexes()
        rows, consecutive = _rows_from_index_list(indexes)

        def _insert(rows: List[int]):
            row = 0
            if direction == 'below':
                row = rows[-1] + 1
            elif direction == 'above':
                row = rows[0]
            else:
                raise ValueError('Unknown direction: {}'.format(str(direction)))

            # bound row number to table row size
            row = min(row, self._model.row_ndx.count)
            self.model().insertRows(row, len(rows), QModelIndex())

        if consecutive:
            _insert(rows)
        else:
            groups = _consecutive_groups(rows)
            for rows in reversed(groups):
                _insert(rows)

    def remove_rows(self):
        if not self._model.row_ndx.is_mutable:
            logger.warning('Calling `remove_rows` on immutable row index')
            return
            
        indexes: List[QModelIndex] = self.selectionModel().selectedIndexes()
        rows, sequential = _rows_from_index_list(indexes)
        # this should filter out any 'virtual rows' at the bottom, if user selected them too
        rows = [row for row in rows if row < self._model.row_ndx.count]
        if not rows:
            return False

        # FIXME: allow user to delete all 'real' rows
        # since we don't care about deleting rows in progress, we check
        # if at leas one 'committed' row will remain after deleting
        num_to_delete = len(rows) - self._model.row_ndx.in_progress_mask.iloc[rows].sum()
        if self._model.row_ndx.count_committed - num_to_delete <= 0:
            # TODO: REFACTOR ME: Handle messaging with loggers maybe
            msg = 'Invalid operation: Table must have at least one data row.'
            logger.error(msg)
            QMessageBox.critical(self, 'ERROR.', msg, QMessageBox.Ok)
            return False

        if sequential:
            self.model().removeRows(rows[0], len(rows), QModelIndex())
        else:
            for row in reversed(rows):
                self.model().removeRows(row, 1, QModelIndex())
    
    def apply_and_close_header_menu(self):
        self.blockSignals(True)
        self._proxy.apply_list_filter(self.header_menu)
        self.blockSignals(False)
        self.header_menu.close()

    def clear_all_filters(self):
        self._proxy.clear_filter_cache()

    def clear_column_filter(self, col_ndx):
        self._proxy.clear_filter_from_column(col_ndx)
        header_widget = self.header_view.header_widgets[col_ndx]
        header_widget.set_filtered(filtered=False)
            
    def filter_by_value(self, row_ndx: int, col_ndx: int):
        cell_val = self.model().data(self.model().index(row_ndx, col_ndx), Qt.DisplayRole)
        self._proxy.set_filter_key_column(col_ndx)
        self._proxy.string_filter(cell_val)

    @property
    def is_dirty(self) -> bool:
        return self._model.is_dirty

    @is_dirty.setter
    def is_dirty(self, value: bool) -> bool:
        if not isinstance(value, bool):
            raise TypeError('`value` is not a bool')
        self._model.is_dirty = value

    @property
    def dataframe_model(self) -> DataFrameModel:
        return self._model

    @property
    def has_mutable_rows(self) -> bool:
        return self.dataframe_model.row_ndx.is_mutable
        
    @property
    def has_virtual_row(self) -> bool:
        return self.dataframe_model.row_ndx.count_virtual > 0

    def filter_list_widget_by_text(self, text):
        self._proxy.filter_list_widget_by_text(text=text)    

    def async_to_excel(self):
        worker = Worker(self.to_excel)
        worker.signals.error.connect(self.on_error)
        self.threadpool.start(worker)

    def to_excel(self, *args, **kwargs):
        logger.info('Exporting to Excel Started...')
        from subprocess import Popen
        rows = self._proxy.accepted.loc[self.df.index]
        columns = self._get_visible_column_names()
        fname = 'temp.xlsx'
        logger.info('Writing to Excel file...')
        self.df.loc[rows, columns].to_excel(fname, 'Output')
        logger.info('Opening Excel...')
        Popen(fname, shell=True)
        logger.info('Exporting to Excel Finished')

    def on_error(self, exc_info: Tuple[Type[BaseException], BaseException, TracebackType]) -> None:
        logger.error(msg='ERROR.', exc_info=exc_info)
        formatted = ' '.join(traceback.format_exception(*exc_info, limit=4))
        QMessageBox.critical(self, 'ERROR.', formatted, QMessageBox.Ok)

    def _get_visible_column_names(self) -> list:
        return [self._df.columns[ndx] for ndx in range(self._df.shape[1]) if not self.isColumnHidden(ndx)]

    def _get_hidden_column_indices(self) -> list:
        return [ndx for ndx in range(self._df.shape[1]) if self.isColumnHidden(ndx)]


def _rows_from_index_list(indexes: List[QModelIndex]) -> Tuple[List[int], bool]:
    rows = sorted(set([index.row() for index in indexes]))
    consecutive = rows[0] + len(rows) - 1 == rows[-1]
    return rows, consecutive


def _consecutive_groups(data: List[int]) -> List[List[int]]:
    groups = []
    for _, g in groupby(data, lambda n, c=count(): n-next(c)):
        groups.append(list(g))
    return groups
