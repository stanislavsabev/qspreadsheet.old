"""Example for how to use the `qspreadsheet` package."""

import sys
from typing import Callable

from PySide2 import QtWidgets, QtGui, QtCore

import pandas as pd
from qspreadsheet import dataframe_view as df_view


class MainWindow(QtWidgets.QMainWindow):
    """Main GUI Window."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        """Init MainWindow object."""
        super().__init__(parent)

        self._org = 'qt'
        self._app = 'qspreadsheet'
        self._default_size = QtCore.QSize(800, 480)

        central_widget = QtWidgets.QWidget(self)
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        central_widget.setLayout(central_layout)

        df = load_data()
        table_widget = df_view.DataFrameView(df=df)

        table_layout = QtWidgets.QHBoxLayout()
        table_layout.addWidget(table_widget)
        table_widget.setParent(table_layout)
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


def load_data():
    area = pd.Series({0 : 423967, 1: 695662, 2: 141297, 3: 170312, 4: 149995})
    pop = pd.Series({0 : 38332521, 1: 26448193, 2: 19651127, 3: 19552860, 4: 12882135})
    states = ['California', 'Texas', 'New York', 'Florida', 'Illinois']
    data = pd.DataFrame({'states': states, 'area': area, 'pop': pop}, index=range(len(states)))
    return data


def main():
    """Entry point for this script."""
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
