from __future__ import annotations

import datetime as dt
import sys

from typing import (
    TYPE_CHECKING, Any, Callable, ClassVar, Dict, List, Optional,
)

import numpy as np
import pandas as pd
import param

from bokeh.models import ColumnDataSource
from pyviz_comms import JupyterComm

from ..reactive import SyncableData
from ..util import isdatetime, lazy_load
from .base import ModelPane

if TYPE_CHECKING:
    from bokeh.document import Document
    from bokeh.model import Model
    from pyviz_comms import Comm


class Vizzu(ModelPane, SyncableData):
    """
    The `Vizzu` pane provides an interactive visualization component for
    large, real-time datasets built on the Vizzu project.

    Reference: https://panel.holoviz.org/reference/panes/Vizzu.html

    :Example:

    >>> Vizzu(df)
    """

    animation = param.Dict(default={}, doc="""
        Animation settings (see https://lib.vizzuhq.com/latest/reference/modules/vizzu.Anim.html).""")

    config = param.Dict(default={}, doc="""
        The config contains all of the parameters needed to render a
        particular static chart or a state of an animated chart
        (see https://lib.vizzuhq.com/latest/reference/interfaces/vizzu.Config.Chart.html).""")

    click = param.Parameter(doc="""
        Data associated with the latest click event.""")

    column_types = param.Dict(default={}, doc="""
        Optional column definitions. If not defined will be inferred
        from the data.""")

    duration = param.Integer(default=500, doc="""
        The config contains all of the parameters needed to render a
        particular static chart or a state of an animated chart.""")

    style = param.Dict(default={}, doc="""
        Style configuration of the chart.""")

    _data_params: ClassVar[List[str]] = ['object']

    _rename: ClassVar[Dict[str, str | None]] = {
        'click': None, 'column_types': None, 'object': None
    }

    _rerender_params: ClassVar[List[str]] = []

    _updates: ClassVar[bool] = True

    def __init__(self, object=None, **params):
        super().__init__(object, **params)
        self._event_handlers = []

    @classmethod
    def applies(cls, object):
        if isinstance(object, dict) and all(isinstance(v, (list, np.ndarray)) for v in object.values()):
            return 0 if object else None
        elif 'pandas' in sys.modules:
            import pandas as pd
            if isinstance(object, pd.DataFrame):
                return 0
        return False

    def _get_data(self):
        if self.object is None:
            return {}, {}
        if isinstance(self.object, dict):
            cols = data = dict(self.object)
        else:
            data = self.object
            cols = ColumnDataSource.from_df(self.object)
        return data, {str(k): v for k, v in cols.items()}

    def _get_columns(self):
        columns = []
        for col, array in self._data.items():
            if col in self.column_types:
                columns.append({'name': col, 'type': self.column_types[col]})
                continue
            if not isinstance(array, np.ndarray):
                array = np.asarray(array)
            kind = array.dtype.kind
            if kind == 'M':
                columns.append({'name': col, 'type': 'datetime'})
            elif kind in 'uif':
                columns.append({'name': col, 'type': 'measure'})
            elif kind in 'bsU':
                columns.append({'name': col, 'type': 'dimension'})
            else:
                if len(array):
                    value = array[0]
                    if isinstance(value, dt.date):
                        columns.append({'name': col, 'type': 'datetime'})
                    elif isdatetime(value) or isinstance(value, pd.Period):
                        columns.append({'name': col, 'type': 'datetime'})
                    elif isinstance(value, str):
                        columns.append({'name': col, 'type': 'dimension'})
                    elif isinstance(value, (float, np.float, int, np.int)):
                        columns.append({'name': col, 'type': 'measure'})
                    else:
                        columns.append({'name': col, 'type': 'dimension'})
                else:
                    columns.append({'name': col, 'type': 'dimension'})
        return columns

    def _get_properties(self, doc, source=None):
        props = super()._get_properties(doc)
        props['duration'] = self.duration
        if source is None:
            props['source'] = ColumnDataSource(data=self._data)
        else:
            source.data = self._data
            props['source'] = source
        return props

    def _process_param_change(self, params):
        if 'object' in params:
            self._processed, self._data = self._get_data()
        if 'object' in params or 'column_types' in params:
            params['columns'] = self._get_columns()
        return super()._process_param_change(params)

    def _get_model(
        self, doc: Document, root: Optional[Model] = None,
        parent: Optional[Model] = None, comm: Optional[Comm] = None
    ) -> Model:
        self._bokeh_model = lazy_load(
            'panel.models.vizzu', 'VizzuChart', isinstance(comm, JupyterComm), root
        )
        model = super()._get_model(doc, root, parent, comm)
        self._register_events('vizzu_event', model=model, doc=doc, comm=comm)
        return model

    def _process_event(self, event):
        self.click = event.data
        for handler in self._event_handlers:
            handler(event.data)

    def _update(self, ref: str, model: Model) -> None:
        pass

    def animate(
        self, anim: Dict[str, Any], options: int | Dict[str, Any] | None = None
    ) -> None:
        """
        Updates the chart with a new configuration.
        """
        if not any(key in anim for key in ('config', 'data', 'style')):
            anim = {'config': anim}
        updates = {}
        for p, value in anim.items():
            if p not in self.param:
                raise ValueError(
                    f'Could not update {p!r}. You must pass either a dictionary '
                    'containing config, data and/or style values OR a single '
                    'config dictionary. '
                )
            updates[p] = dict(getattr(self, p), **value)
        if isinstance(options, int):
            self.duration = options
        elif isinstance(options, dict):
            self.animation = options
        self.param.update(updates)

    # Public API

    def on_click(self, callback: Callable[[Dict], None]):
        """
        Register a callback to be executed when any element in the
        chart is clicked on.

        Arguments
        ---------
        callback: (callable)
            The callback to run on click events.
        """
        self._event_handlers.append(callback)
