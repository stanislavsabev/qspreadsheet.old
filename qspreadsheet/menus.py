import logging
import os
import sys
from typing import List, Optional, Tuple

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from qspreadsheet import resources_rc
from qspreadsheet.common import LEFT, SER, standard_icon
from qspreadsheet.custom_widgets import LabeledLineEdit
from qspreadsheet.dataframe_model import DataFrameModel
from qspreadsheet.worker import Worker

logger = logging.getLogger(__name__)


class FilterWidgetAction(QWidgetAction):
    """Checkboxed list filter menu"""

    all_deselected = Signal(bool)

    def __init__(self, parent=None) -> None:
        """Checkbox list filter menu

            Arguments
            ----------
            
            parent: (Widget)
                Parent
            
            menu: (QMenu)
                Menu object this list is located on
        """
        super(FilterWidgetAction, self).__init__(parent)

        # Build Widgets
        widget = QWidget()
        layout = QVBoxLayout()

        self.str_filter = LabeledLineEdit('Filter', parent=parent)
        layout.addWidget(self.str_filter)

        self.list = QListWidget(widget)
        self.list.setStyleSheet("""
            QListView::item:selected {
                background: rgb(195, 225, 250);
                color: rgb(0, 0, 0);
            } """)
        self.list.setMinimumHeight(150)
        self.list.setUniformItemSizes(True)

        layout.addWidget(self.list)

        # This button in made visible if the number 
        # of items to show is more than the initial limit
        btn = QPushButton('Not all items showing')
        
        btn.setIcon(standard_icon('MessageBoxWarning'))
        btn.setVisible(False)
        layout.addWidget(btn)
        self.show_all_btn = btn
        self.select_all_item: Optional[QListWidgetItem] = None

        widget.setLayout(layout)
        self.setDefaultWidget(widget)

        # Signals/slots
        self.list.itemChanged.connect(self.on_listitem_changed)
        self.num_checked = 0
        
    def addItem(self, item: QListWidgetItem):
        if item.checkState() == Qt.Checked:
            self.num_checked += 1
        self.list.addItem(item)

    def addSelectAllItem(self, state: Qt.CheckState) -> QListWidgetItem:
        """Adding '(Select All)' item at the beginning of the QListWidget"""
        item = QListWidgetItem('(Select All)')
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(state)
        self.select_all_item = item
        self.list.insertItem(0, item)

        return item

    def clear(self):
        self.list.clear()
        self.num_checked = 0
        self.all_deselected.emit(True)

    @property
    def list_items_count(self) -> int:
        """Number of list items, excluding the '(Select All)' item"""
        return self.list.count() - 1
        
    def on_listitem_changed(self, item: QListWidgetItem):

        self.list.blockSignals(True)
        if item is self.select_all_item:
            # Handle "select all" item click
            state = item.checkState()
            # Select/deselect all items
            for i in range(self.list.count()):
                itm = self.list.item(i)
                if itm is self.select_all_item:
                    continue
                itm.setCheckState(state)
            
            all_unchecked = (state == Qt.Unchecked)
            # -1 is for the select_all_item
            self.num_checked = 0 if all_unchecked else self.list_items_count
        else:
            # Non "select all" item 
            if item.checkState() == Qt.Unchecked:
                self.num_checked -= 1
            elif item.checkState() == Qt.Checked:
                self.num_checked += 1
            assert(self.num_checked >= 0)
            
            # figure out what "select all" should be
            state = Qt.Checked if self.num_checked == self.list_items_count else Qt.Unchecked
            # if state changed
            if state != self.select_all_item.checkState():
                self.select_all_item.setCheckState(state)

        if self.num_checked == 0:
            self.all_deselected.emit(True)
        else:
            self.all_deselected.emit(False)

        self.list.scrollToItem(item)
        self.list.blockSignals(False)

    def values(self) -> List[str]:
        checked = []
        for i in range(self.list.count()):
            itm = self.list.item(i)
            if itm is self.select_all_item:
                continue
            if itm.checkState() == Qt.Checked:
                checked.append(itm.text())
        return checked
