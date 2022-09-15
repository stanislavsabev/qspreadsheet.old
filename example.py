"""Example for how to use the `qspreadsheet` package."""

import sys
from typing import Callable

from PySide2 import QtWidgets, QtGui, QtCore
import pandas as pd

from qspreadsheet import custom_widgets, dataframe_view as df_view
from qspreadsheet import delegates


class MainWindow(QtWidgets.QMainWindow):
    """Main GUI Window."""

    def __init__(self, table_view: QtWidgets.QTableView = None,
                 parent: QtWidgets.QWidget = None):
        """Init MainWindow object."""
        super().__init__(parent)

        self._org = 'qt'
        self._app = 'qspreadsheet'
        self._default_size = QtCore.QSize(800, 480)

        central_widget = QtWidgets.QWidget(self)
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        central_widget.setLayout(central_layout)

        table_layout = QtWidgets.QHBoxLayout()
        if not table_view:
            table_view = QtWidgets.QTableView()
        table_layout.addWidget(table_view)
        table_view.setParent(table_layout)
        central_layout.addLayout(table_layout)

        self.setCentralWidget(central_widget)
        self.setWindowTitle('qspreadsheet')
        self.apply_settings(self.load_settings)

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Pyside2-closeEvent."""
        self.apply_settings(self.save_settings)
        event.accept()

    def apply_settings(self, func: Callable[[QtCore.QSettings], None]):
        """Apply window settings ot own group and close it."""
        settings = QtCore.QSettings(QtCore.QSettings.IniFormat,
                                    QtCore.QSettings.UserScope,
                                    self._org,
                                    self._app)
        settings.beginGroup('MainWindow')
        func(settings)
        settings.endGroup()

    def save_settings(self, settings: QtCore.QSettings):
        """Save window settings like size and position."""
        settings.setValue('size', self.size())
        settings.setValue('pos', self.pos())

    def load_settings(self, settings: QtCore.QSettings):
        """Load window settings like size and position."""
        self.resize(QtCore.QSize(settings.value('size', self._default_size)))  # type: ignore
        self.move(QtCore.QPoint(settings.value('pos', QtCore.QPoint(200, 200))))  # type: ignore


def load_df():
    area = pd.Series({0 : 423967, 1: 695662, 2: 141297, 3: 170312, 4: 149995})
    pop = pd.Series({0 : 38332521, 1: 26448193, 2: 19651127, 3: 19552860, 4: 12882135})
    states = ['California', 'Texas', 'New York', 'Florida', 'Illinois']
    data = {'states': states, 'area': area, 'pop': pop}
    df = pd.DataFrame(data=data)
    df['overcrowded'] = (df['pop'] / df['area'] > 100)
    return df


class BoolToYesNoDelegate(delegates.BoolDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.choices = ['Yes', 'No']
        self._default = ''

    def setEditorData(self, editor: QtWidgets.QComboBox, index: QtCore.QModelIndex):
        model_value = index.model().data(index, QtCore.Qt.EditRole)
        if pd.isnull(model_value):
            editor.setCurrentIndex(self.default_value(index))
            return
        value = 'Yes' if model_value else 'No'
        editor.setCurrentIndex(self.choices.index(value))

    def display_data(self, index, value):
        if pd.isnull(value):
            return ''
        return 'Yes' if value else 'No'

    def setModelData(self, editor: QtWidgets.QComboBox,
                     model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex):
        value = self.choices[editor.currentIndex()]
        model.setData(index, True if value == 'Yes' else False)


def main():
    """Entry point for this script."""
    app = QtWidgets.QApplication(sys.argv)
    df = load_df()
    table_view = df_view.DataFrameView(df=df)
    table_view.set_column_delegate_for(
        'overcrowded', BoolToYesNoDelegate())
    table_view.set_column_delegate_for(
        'states', delegates.StringDelegate())
    table_view.set_columns_edit_state(['pop', 'area'], False)
    

    window = MainWindow(table_view=table_view)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
