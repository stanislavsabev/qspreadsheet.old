from functools import partial
import sys
from PySide2 import QtCore, QtGui, QtWidgets

class FilterHeader(QtWidgets.QHeaderView):
    filterActivated = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self._editors = []
        self._padding = 2
        self.setStretchLastSection(False)
        # self.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.setDefaultAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.setSortIndicatorShown(False)
        self.sectionResized.connect(self.adjustPositions)
        parent.horizontalScrollBar().valueChanged.connect(
            self.adjustPositions)

    def setFilterBoxes(self, count):
        while self._editors:
            editor = self._editors.pop()
            editor.deleteLater()
        for index in range(count):
            editor = QtWidgets.QPushButton(self.parent())
            editor.setFixedSize(20, 20)
            editor.setObjectName(f'filter button {index}')
            editor.clicked.connect(
                partial(self.filterActivated.emit, editor.objectName()))
            self._editors.append(editor)
        self.adjustPositions()

    def sizeHint(self):
        size = super().sizeHint()
        if self._editors:
            # height = self._editors[0].sizeHint().height()
            width = self._editors[0].sizeHint().width()
            # size.setHeight(size.height() + height + self._padding)
            size.setWidth(size.width() + width + self._padding)
        return size

    def updateGeometries(self):
        if self._editors:
            # height = self._editors[0].sizeHint().height()
            width = self._editors[0].sizeHint().width()
            # self.setViewportMargins(0, 0, 0, height + self._padding)
            # margins = QtCore.QMargins(0, 0, width + self._padding, height + self._padding)
            self.setViewportMargins(0, 0, width + self._padding, 0)
        else:
            self.setViewportMargins(0, 0, 0, 0)
        super().updateGeometries()
        self.adjustPositions()

    def adjustPositions(self):
        for index, editor in enumerate(self._editors):
            # height = editor.sizeHint().height()
            width = editor.width()
            section_width = self.sectionSizeFromContents(index).boundedTo()
            editor.move(
                self.sectionPosition(index) + self.offset() + width + self._padding, 0)
            # editor.resize(width, height)

    def filterText(self, index):
        if 0 <= index < len(self._editors):
            return self._editors[index].text()
        return ''

    def setFilterText(self, index, text):
        if 0 <= index < len(self._editors):
            self._editors[index].setText(text)

    def clearFilters(self):
        for editor in self._editors:
            editor.clear()


class Window(QtWidgets.QWidget):
    def __init__(self):
        super(Window, self).__init__()
        self.view = QtWidgets.QTableView()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.view)
        header = FilterHeader(self.view)
        self.view.setHorizontalHeader(header)
        model = QtGui.QStandardItemModel(self.view)
        model.setHorizontalHeaderLabels('One Two Three Four Five'.split())
        self.view.setModel(model)
        header.setFilterBoxes(model.columnCount())
        header.filterActivated.connect(self.handleFilterActivated)

    def handleFilterActivated(self, name):
        print('Filter clicked')
        if name:
            print(name)


if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    window.setGeometry(600, 100, 600, 300)
    window.show()
    sys.exit(app.exec_())