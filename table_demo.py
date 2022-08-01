from pyqttable import PyQtTable
from PyQt5 import QtWidgets
import pandas as pd 

my_config = [
    {
        'key': 'area',                        # same as DataFrame column
        'name': 'Area',                       # shown as table header
        'type': int,                            # string variable
        'editable': True,                      # read-only
    },
    {
        'key': 'pop',                        # same as DataFrame column
        'name': 'POPULATION',                       # shown as table header
        'type': int,                            # string variable
        'editable': True,                      # read-only
    },
    {
        'key': 'states',                        # same as DataFrame column
        'name': 'States',                       # shown as table header
        'type': str,                            # string variable
        'editable': True,                      # read-only
    },
]


def get_data():
    area = pd.Series({0 : 423967, 1: 695662, 2: 141297, 3: 170312, 4: 149995})
    pop = pd.Series({0 : 38332521, 1: 26448193, 2: 19651127, 3: 19552860, 4: 12882135})
    states = ['California', 'Texas', 'New York', 'Florida', 'Illinois']
    data = pd.DataFrame({'states':states, 'area':area, 'pop':pop}, index=range(len(states)))
    return data
    
    
def main():
    app = QtWidgets.QApplication([])
    table_widget = PyQtTable(
        parent=None,              # parent widget
        column_config=my_config,  # column configurations
        show_filter=True,         # show filter in header
        sortable=True,            # sortable column (triggered by right click)
        draggable=True           # draggable column
    )

    data = get_data()
    table_widget.set_data(data)

    table_widget.show()
    return app.exec_()


if __name__ == '__main__':
    main()