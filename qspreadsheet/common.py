import pandas as pd 
from typing import TypeVar, Union
import collections
import six
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QApplication, QStyle


MAX_INT = 2147483647
MAX_FLOAT = 3.4028234664e+38
LEFT, ABOVE = range(2)

DF = TypeVar('DF', bound=pd.DataFrame)
SER = TypeVar('SER', bound=pd.Series)


def is_iterable(arg):
    return (
        isinstance(arg, collections.Iterable) 
        and not isinstance(arg, six.string_types)
    )

def standard_icon(icon_name: str) -> QIcon:
    '''Convenience function to get standard icons from Qt'''
    if not icon_name.startswith('SP_'):
        icon_name = 'SP_' + icon_name
    icon = getattr(QStyle, icon_name, None)
    if icon is None:
        raise Exception("Unknown icon {}".format(icon_name))
    return QApplication.style().standardIcon(icon)


def pandas_obj_insert_rows(obj: Union[DF, SER], at_index: int,
                           new_rows: Union[DF, SER]) -> Union[DF, SER]:
    above = obj.iloc[0: at_index]
    below = obj.iloc[at_index:]
    below.index = below.index + new_rows.index.size
    obj = pd.concat([above, new_rows, below])

    # This is needed, because during contatenation, pandas is
    # coercing pd.NA null values to None
    obj.iloc[new_rows.index] = new_rows
    return obj


def pandas_obj_remove_rows(obj: Union[DF, SER], row: int, count: int) -> Union[DF, SER]:
    index_rows = range(row, row + count)
    obj = obj.drop(index=obj.index[index_rows])
    obj = obj.reset_index(drop=True)
    return obj
