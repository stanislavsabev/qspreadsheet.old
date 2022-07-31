import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Union

import numpy as np
import pandas as pd
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from qspreadsheet.common import DF, MAX_FLOAT, MAX_INT
from qspreadsheet.custom_widgets import RichTextLineEdit

DateLike = Union[str, datetime, pd.Timestamp, QDate]
logger = logging.getLogger(__name__)


class ColumnDelegate(QStyledItemDelegate):

    def __init__(self, parent=None) -> None:
        super(ColumnDelegate, self).__init__(parent)

    def display_data(self, index: QModelIndex, value: Any) -> str:
        if pd.isnull(value):
            return '.NA'
        return str(value)

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return Qt.AlignLeft | Qt.AlignVCenter

    def background_brush(self, index: QModelIndex) -> QBrush:
        return None

    def foreground_brush(self, index: QModelIndex) -> QBrush:
        return None

    def font(self, index: QModelIndex) -> QFont:
        return None

    def null_value(self) -> Any:
        return None

    def default_value(self, index: QModelIndex) -> Any:
        return None

    def to_nullable(self) -> 'NullableDelegate':
        return NullableDelegate(self)

    def to_non_nullable(self) -> 'ColumnDelegate':
        return self


class NullableDelegate(ColumnDelegate):

    def __init__(self, column_delegate: ColumnDelegate):
        super(NullableDelegate, self).__init__(column_delegate.parent())
        self._delegate = column_delegate
        self.checkbox: Optional[QCheckBox] = None
        self._editor: Optional[QWidget] = None

    def __repr__(self) -> str:
        managed_name = self._delegate.__class__.__name__
        return '{}[{}] at {}'.format(
            self.__class__.__name__, managed_name, hex(id(self)))

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        nullable_editor = QWidget(parent)
        nullable_editor.setAutoFillBackground(True)

        self.checkbox = QCheckBox('')
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(self.on_checkboxStateChanged)
        
        editor = self._delegate.createEditor(parent, option, index)
        editor.setParent(nullable_editor)
        editor.setSizePolicy(QSizePolicy.MinimumExpanding,
                             QSizePolicy.MinimumExpanding)
        editor.setFocus(Qt.MouseFocusReason)
        self._editor = editor

        layout = QHBoxLayout()
        layout.addWidget(self.checkbox)
        layout.addWidget(editor)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        nullable_editor.setLayout(layout)
        return nullable_editor

    def on_checkboxStateChanged(self, state: int):
        isnull = (state == Qt.Unchecked)
        self._editor.setEnabled(not isnull)

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        self._delegate.setEditorData(self._editor, index)

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex):
        if self.checkbox.checkState() == Qt.Checked:
            self._delegate.setModelData(self._editor, model, index)
        elif self.checkbox.checkState() == Qt.Unchecked:
            model.setData(index, self._delegate.null_value())

    def display_data(self, index: QModelIndex, value: Any) -> Any:
        return self._delegate.display_data(index, value)

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return self._delegate.alignment(index)

    def default_value(self, index: QModelIndex) -> Any:
        return self._delegate.default_value(index)

    def null_value(self) -> Any:
        return self._delegate.null_value()

    def to_nullable(self) -> 'NullableDelegate':
        return self

    def to_non_nullable(self) -> ColumnDelegate:
        return self._delegate


class MasterDelegate(ColumnDelegate):

    def __init__(self, parent=None):
        super(MasterDelegate, self).__init__(parent=parent)
        self.delegates: Dict[int, ColumnDelegate] = {}

    def add_column_delegate(self, column_index: int, delegate: ColumnDelegate):
        delegate.setParent(self)
        self.delegates[column_index] = delegate

    def remove_column_delegate(self, column_index: int):
        delegate = self.delegates.pop(column_index, None)
        if delegate is not None:
            delegate.deleteLater()
            del delegate

    def paint(self, painter, option, index):
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            delegate.paint(painter, option, index)
        else:
            QStyledItemDelegate.paint(self, painter, option, index)

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.createEditor(parent, option, index)
        else:
            return QStyledItemDelegate.createEditor(self, parent, option,
                                                    index)

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            delegate.setEditorData(editor, index)
        else:
            QStyledItemDelegate.setEditorData(self, editor, index)

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex):
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            delegate.setModelData(editor, model, index)
        else:
            QStyledItemDelegate.setModelData(self, editor, model, index)

    def display_data(self, index: QModelIndex, value: Any) -> str:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.display_data(index, value)
        else:
            return super().display_data(index, value)

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.alignment(index)
        return super().alignment(index)

    def background_brush(self, index: QModelIndex) -> QBrush:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.background_brush(index)
        return super().background_brush(index)

    def foreground_brush(self, index: QModelIndex) -> QBrush:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.foreground_brush(index)
        return super().foreground_brush(index)

    def font(self, index: QModelIndex) -> QFont:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.font(index)
        return super().font(index)

    def default_value(self, index: QModelIndex) -> Any:
        delegate = self.delegates.get(index.column())
        if delegate is not None:
            return delegate.default_value(index)
        return super().default_value(index)

    def null_value(self) -> Any:
        return {ndx: delegate.null_value()
                for ndx, delegate in self.delegates.items()}

    @property
    def non_nullable_delegates(self):
        return {ndx: delegate
                for ndx, delegate in self.delegates.items()
                if not isinstance(delegate, NullableDelegate)}

    @property
    def nullable_delegates(self):
        return {ndx: delegate
                for ndx, delegate in self.delegates.items()
                if isinstance(delegate, NullableDelegate)}

    def to_nullable(self) -> 'NullableDelegate':
        return self
# endregion MasterDelegate specific


# region Type delegates
class IntDelegate(ColumnDelegate):

    def __init__(self, parent=None,
                 minimum: Optional[int] = None, maximum: Optional[int] = None):
        super(IntDelegate, self).__init__(parent)
        self.minimum = minimum or -MAX_INT
        self.maximum = maximum or MAX_INT
        self._default = 0

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QSpinBox(parent)
        editor.setRange(self.minimum, self.maximum)
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return editor

    def setEditorData(self, editor: QSpinBox, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                          else int(model_value)    
        editor.setValue(value)

    def setModelData(self, editor: QSpinBox, model: QAbstractItemModel, index: QModelIndex):
        editor.interpretText()
        model.setData(index, editor.value())

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return Qt.AlignRight | Qt.AlignVCenter

    def default_value(self, index: QModelIndex) -> Any:
        return self._default

    def null_value(self) -> Any:
        return pd.NA


class FloatDelegate(ColumnDelegate):

    def __init__(self, parent=None,
                 minimum: Optional[float] = None,
                 maximum: Optional[float] = None,
                 edit_precision: int = 4,
                 display_precision: int = 2):
        super(FloatDelegate, self).__init__(parent)
        self.minimum = minimum or -MAX_FLOAT
        self.maximum = maximum or MAX_FLOAT
        self.edit_precision = edit_precision
        self.display_precision = display_precision
        self._default = 0

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QDoubleSpinBox(parent)
        editor.setRange(self.minimum, self.maximum)
        editor.setDecimals(self.edit_precision)
        editor.setSingleStep(0.1)
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return editor

    def setEditorData(self, editor: QDoubleSpinBox, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                          else float(model_value)
        editor.setValue(value)

    def setModelData(self, editor: QDoubleSpinBox, model: QAbstractItemModel, index: QModelIndex):
        editor.interpretText()
        value = editor.value()
        model.setData(index, value)

    def display_data(self, index: QModelIndex, value: Any) -> str:
        if pd.isnull(value):
            return super().display_data(index, value)
        return '{0:.{1}f}'.format(value, self.display_precision)

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return Qt.AlignRight | Qt.AlignVCenter

    def default_value(self, index: QModelIndex) -> Any:
        return self._default

    def null_value(self) -> Any:
        return np.nan


class BoolDelegate(ColumnDelegate):

    def __init__(self, parent=None) -> None:
        super(BoolDelegate, self).__init__(parent)
        self.choices = [True, False]
        self._default = False

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QComboBox(parent)
        editor.addItems(list(map(str, self.choices)))
        editor.setEditable(True)
        editor.lineEdit().setReadOnly(True)
        editor.lineEdit().setAlignment(self.alignment(index))
        return editor

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                          else self.choices.index(model_value)
        editor.setCurrentIndex(value)

    def setModelData(self, editor: QComboBox, model: QAbstractItemModel, index: QModelIndex):
        value = self.choices[editor.currentIndex()]
        model.setData(index, value)

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return Qt.AlignCenter

    def default_value(self, index: QModelIndex) -> Any:
        return self.choices.index(self._default)

    def to_nullable(self) -> 'NullableDelegate':
        return self

    def null_value(self) -> Any:
        return pd.NA


class DateDelegate(ColumnDelegate):

    def __init__(self, parent=None,
                 minimum: Optional[DateLike] = None, maximum: Optional[DateLike] = None,
                 date_format='yyyy-MM-dd'):
        super(DateDelegate, self).__init__(parent)
        self.minimum = as_qdate(minimum) if minimum else QDate(1970, 1, 1)
        self.maximum = as_qdate(maximum) if maximum else QDate(9999, 1, 1)
        self.date_format = date_format
        self._default = QDate.currentDate()

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QDateEdit(parent)
        editor.setDateRange(self.minimum, self.maximum)
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        editor.setDisplayFormat(self.date_format)
        editor.setCalendarPopup(True)
        return editor

    def setEditorData(self, editor: QDateEdit, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                          else as_qdate(model_value)
        editor.setDate(value)

    def setModelData(self, editor: QDateEdit, model: QAbstractItemModel, index: QModelIndex):
        model.setData(index, pd.to_datetime(editor.date().toPython()))

    def display_data(self, index: QModelIndex, value: pd.Timestamp) -> Any:
        if pd.isnull(value):
            return '.NaT'
        result = as_qdate(value).toString(self.date_format)
        return result

    def alignment(self, index: QModelIndex) -> Qt.Alignment:
        return Qt.AlignRight | Qt.AlignVCenter

    def default_value(self, index: QModelIndex) -> Any:
        return self._default

    def null_value(self) -> Any:
        return pd.NaT


class StringDelegate(ColumnDelegate):

    def __init__(self, parent=None) -> None:
        super(StringDelegate, self).__init__(parent)
        self._default = ''

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                            else str(model_value)
        editor.setText(value)

    def setModelData(self, editor: QLineEdit, model: QAbstractItemModel, index: QModelIndex):
        model.setData(index, editor.text())

    def default_value(self, index: QModelIndex) -> Any:
        return self._default


class RichTextDelegate(ColumnDelegate):

    def __init__(self, parent=None):
        super(RichTextDelegate, self).__init__(parent)
        self._default = ''

    def paint(self, painter, option, index: QModelIndex):
        text = index.model().data(index, Qt.DisplayRole)
        palette = QApplication.palette()
        document = QTextDocument()
        document.setDefaultFont(option.font)
        if option.state & QStyle.State_Selected:
            document.setHtml("<font color={}>{}</font>".format(
                palette.highlightedText().color().name(), text))
        else:
            document.setHtml(text)
        painter.save()
        color = (palette.highlight().color()
                 if option.state & QStyle.State_Selected
                 else QColor(index.model().data(index,
                                                Qt.BackgroundColorRole)))
        painter.fillRect(option.rect, color)
        painter.translate(option.rect.x(), option.rect.y())
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index: QModelIndex):
        text = index.model().data(index)
        document = QTextDocument()
        document.setDefaultFont(option.font)
        document.setHtml(text)
        return QSize(document.idealWidth() + 5,
                     option.fontMetrics.height())

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = RichTextLineEdit(parent)
        return editor

    def setEditorData(self, editor: RichTextLineEdit, index: QModelIndex):
        model_value = index.model().data(index, Qt.EditRole)
        value = self.default_value(index) if pd.isnull(model_value) \
                                            else model_value
        editor.setHtml(value)

    def setModelData(self, editor: RichTextLineEdit, model: QAbstractItemModel, index: QModelIndex):
        model.setData(index, editor.toSimpleHtml())

    def to_nullable(self) -> 'NullableDelegate':
        return self

    def default_value(self, index: QModelIndex) -> Any:
        return self._default
# endregion Type delegates

def automap_delegates(df: DF,
                      nullable: Union[bool, Mapping[Any, bool]] = True
                      ) -> Dict[Any, ColumnDelegate]:
    
    dtypes = df.dtypes.astype(str)

    delegates = {}
    for columnname, dtype in dtypes.items():
        for key, delegate_class in default_delegates.items():
            if key in dtype:
                delegate = delegate_class()
                break
        else:
            delegate = StringDelegate()

        delegates[columnname] = delegate

    if isinstance(nullable, bool):
        if nullable:
            delegates = {column: delegate.to_nullable()
                              for column, delegate in delegates.items()}
    elif isinstance(nullable, Mapping):
        for columnname, delegate in delegates.items():
            if nullable.get(columnname, False):
                delegates[columnname] = delegate.to_nullable()
    else:
        raise TypeError('Invalid type for `nullable`.')


    return delegates


def as_qdate(datelike: DateLike, format: Optional[str] = None) -> QDate:
    '''Converts date-like value to QDate

        Parameters
        ----------
        dt: {str, datetime, pd.Timestamp, QDate}: value to convert

        format: {str}: default=None. Format must be provided if dt is `str`.

        Returns
        -------
        `QDate`
    '''
    if isinstance(datelike, str):
        datelike = datetime.strptime(datelike, format)
    return datelike if isinstance(datelike, QDate) else QDate(datelike.year, datelike.month, datelike.day)

default_delegates = dict((
        ('object', StringDelegate),
        ('int', IntDelegate),
        ('float', FloatDelegate),
        ('datetime', DateDelegate),
        ('bool', BoolDelegate),
    ))